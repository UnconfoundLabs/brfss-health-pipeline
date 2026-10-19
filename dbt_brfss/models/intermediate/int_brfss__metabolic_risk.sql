/*
  int_brfss__metabolic_risk
  ─────────────────────────
  Composite metabolic risk score (0-5) per respondent.

  Risk components (each scored 0 or 1):
    1. Obesity       — bmi_category = 'Obese'
    2. Hypertension  — has_hypertension = true
    3. Inactivity    — physical_activity_index = 'Inactive'
    4. Poor diet     — vegetable (VEGETAB2) consumption less than once per day
    5. Diabetes      — is_diagnosed_diabetic = true

  Score is NULL if all five inputs are NULL (no data for respondent).
*/

with

staging as (
    select
        respondent_id,
        survey_year,
        llcpwt,
        bmi_category,
        has_hypertension,
        physical_activity_index,
        any_exercise_past_30d,
        fruit_frequency,
        vegetable_frequency,
        diabetes_status
    from {{ ref('stg_brfss__respondents') }}
),

-- Join diabetes flags for the diabetes component
diabetes as (
    select respondent_id, is_diagnosed_diabetic
    from {{ ref('int_brfss__diabetes_flags') }}
),

scored as (
    select
        s.respondent_id,
        s.survey_year,
        s.llcpwt,

        -- Individual risk flags (cast NULL inputs to 0 for scoring)
        case when s.bmi_category = 'Obese'               then 1 else 0 end  as obese_flag,
        case when s.has_hypertension = true              then 1 else 0 end  as hypertension_flag,
        case when s.physical_activity_index = 'Inactive' then 1 else 0 end  as inactive_flag,
        case when s.any_exercise_past_30d = false        then 1 else 0 end  as no_exercise_flag,
        case when d.is_diagnosed_diabetic = true         then 1 else 0 end  as diabetes_flag,

        -- Poor diet: "other vegetables" (VEGETAB2) eaten less than once per day.
        -- vegetable_frequency is already in times/day (see stg_brfss__respondents).
        -- NULL (module not asked that year, DK/refused) scores 0, like the other flags.
        case
            when s.vegetable_frequency is not null and s.vegetable_frequency < 1 then 1
            else 0
        end                                                                  as poor_diet_flag,

        -- Track whether we have any data to score (avoid 0 masking true nulls)
        case when
            s.bmi_category is null
            and s.has_hypertension is null
            and s.physical_activity_index is null
            and d.is_diagnosed_diabetic is null
        then true else false end                                             as all_null

    from staging s
    left join diabetes d using (respondent_id)
),

final as (
    select
        respondent_id,
        survey_year,
        llcpwt,
        obese_flag,
        hypertension_flag,
        inactive_flag,
        no_exercise_flag,
        diabetes_flag,
        poor_diet_flag,

        case
            when all_null then null
            else obese_flag + hypertension_flag + inactive_flag + diabetes_flag + poor_diet_flag
        end                                         as metabolic_risk_score,

        case
            when all_null then null
            when (obese_flag + hypertension_flag + inactive_flag + diabetes_flag + poor_diet_flag) >= 3
                then true
            else false
        end                                         as high_metabolic_risk

    from scored
)

select * from final
