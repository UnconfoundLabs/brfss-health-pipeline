/*
  stg_brfss__respondents
  ──────────────────────
  One row per BRFSS survey respondent per year.

  Transformations applied here:
    1. Rename raw CDC variable names to readable SQL column names
    2. Decode integer codes to human-readable labels (CASE WHEN)
    3. Fix BMI units: _BMI5 is stored as BMI * 100 (e.g. 2500 = 25.0)
       and convert fruit/vegetable frequency codes to times per day
    4. Null out refused/don't-know codes so downstream can use IS NULL safely
    5. Filter records with zero or missing survey weight
    6. Join state FIPS codes to state name/abbreviation
    7. Add synthetic respondent_id for downstream joins
*/

with

raw as (
    select * from {{ source('brfss_raw', 'brfss_all') }}
),

state_codes as (
    select
        cast(fips_code as integer) as fips_code,
        state_abbr,
        state_name
    from {{ ref('brfss_state_codes') }}
),

decoded as (
    select
        -- ── Survey metadata ────────────────────────────────────────────────
        survey_year,
        cast(state as integer)          as state_fips,
        cast(imonth as integer)         as interview_month,
        cast(iyear as integer)          as interview_year,

        -- ── Survey design variables (never null these out) ─────────────────
        llcpwt,
        ststr,
        psu,

        -- ── Diabetes outcomes ──────────────────────────────────────────────
        case cast(diabete4 as integer)
            when 1 then 'Diagnosed'
            when 2 then 'Gestational Only'
            when 3 then 'No'
            when 4 then 'Prediabetes'
            else        'Unknown'          -- 7=Don't know, 9=Refused, NULL
        end                                as diabetes_status,

        case cast(prediab2 as integer)
            when 1 then true
            when 2 then false
            else        null
        end                                as has_prediabetes,

        case cast(insulin1 as integer)
            when 1 then true
            when 2 then false
            else        null
        end                                as takes_insulin,

        -- ── Body metrics ───────────────────────────────────────────────────
        -- CDC stores BMI as integer * 100; 9999 = missing
        case
            when cast(bmi5 as integer) in (9999) then null
            when bmi5 is null                    then null
            else round(cast(bmi5 as double) / 100.0, 1)
        end                                as bmi_calc,

        case cast(bmi5cat as integer)
            when 1 then 'Underweight'
            when 2 then 'Normal'
            when 3 then 'Overweight'
            when 4 then 'Obese'
            else        null
        end                                as bmi_category,

        -- ── Cardiovascular / comorbidities ─────────────────────────────────
        case cast(rfhype6 as integer)
            when 1 then false   -- No hypertension
            when 2 then true    -- Yes hypertension
            else        null
        end                                as has_hypertension,

        case cast(cvdcrhd4 as integer)
            when 1 then true
            when 2 then false
            else        null
        end                                as has_coronary_heart_disease,

        -- ── Physical activity ──────────────────────────────────────────────
        case cast(exerany2 as integer)
            when 1 then true
            when 2 then false
            else        null
        end                                as any_exercise_past_30d,

        case cast(paindx3 as integer)
            when 1 then 'Met Aerobic Recommendations'
            when 2 then 'Insufficiently Active'
            when 3 then 'Inactive'
            else        null
        end                                as physical_activity_index,

        -- ── Diet (rotating core: NULL in years the module was not asked) ───
        -- Frequency codes converted to times per day; see brfss_times_per_day macro
        {{ brfss_times_per_day('fruit2') }}   as fruit_frequency,
        {{ brfss_times_per_day('vegetab2') }} as vegetable_frequency,

        -- ── Demographics ───────────────────────────────────────────────────
        case cast(sexvar as integer)
            when 1 then 'Male'
            when 2 then 'Female'
            else        'Unknown'
        end                                as sex,

        case cast(ageg5yr as integer)
            when 1  then '18-24'
            when 2  then '25-29'
            when 3  then '30-34'
            when 4  then '35-39'
            when 5  then '40-44'
            when 6  then '45-49'
            when 7  then '50-54'
            when 8  then '55-59'
            when 9  then '60-64'
            when 10 then '65-69'
            when 11 then '70-74'
            when 12 then '75-79'
            when 13 then '80+'
            else         null
        end                                as age_group,

        case cast(race1 as integer)
            when 1 then 'White Non-Hispanic'
            when 2 then 'Black Non-Hispanic'
            when 3 then 'AI/AN Non-Hispanic'
            when 4 then 'Asian Non-Hispanic'
            when 5 then 'NHPI Non-Hispanic'
            when 6 then 'Other/Multiracial Non-Hispanic'
            when 7 then 'Hispanic'
            else        null
        end                                as race_ethnicity,

        case cast(racegr3 as integer)
            when 1 then 'White Non-Hispanic'
            when 2 then 'Black Non-Hispanic'
            when 3 then 'Hispanic'
            when 4 then 'Other Non-Hispanic'
            when 5 then 'Multiracial Non-Hispanic'
            else        null
        end                                as race_ethnicity_collapsed,

        case cast(educa as integer)
            when 1 then 'Never Attended / Kindergarten'
            when 2 then 'Grades 1-8'
            when 3 then 'Grades 9-11'
            when 4 then 'High School Graduate / GED'
            when 5 then 'Some College'
            when 6 then 'College Graduate'
            else        null
        end                                as education_level,

        case cast(income3 as integer)
            when 1  then '<$10,000'
            when 2  then '$10,000-<$15,000'
            when 3  then '$15,000-<$20,000'
            when 4  then '$20,000-<$25,000'
            when 5  then '$25,000-<$35,000'
            when 6  then '$35,000-<$50,000'
            when 7  then '$50,000-<$75,000'
            when 8  then '$75,000-<$100,000'
            when 9  then '$100,000-<$150,000'
            when 10 then '$150,000-<$200,000'
            when 11 then '≥$200,000'
            else         null
        end                                as income_group,

        case cast(urbstat as integer)
            when 1 then 'Urban'
            when 2 then 'Rural'
            else        null
        end                                as urban_rural

    from raw
    where llcpwt > 0   -- exclude zero-weight respondents
),

final as (
    select
        row_number() over ()             as respondent_id,
        d.*,
        s.state_abbr,
        s.state_name
    from decoded d
    left join state_codes s on d.state_fips = s.fips_code
)

select * from final
