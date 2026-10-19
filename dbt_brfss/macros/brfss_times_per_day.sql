/*
  brfss_times_per_day(column)
  ───────────────────────────
  Converts a BRFSS food-frequency code (FRUIT2, FRUITJU2, VEGETAB2) to times per day.

  BRFSS codebook coding (2021/2023):
    101-199  times per day   (1__)   → code - 100
    201-299  times per week  (2__)   → (code - 200) / 7
    300      less than once a month  → 0
    301-399  times per month (3__)   → (code - 300) / 30
    555      never                   → 0
    777/999  don't know / refused    → NULL
    blank    not asked / missing     → NULL

  The /30 month convention matches CDC's calculated _FRUTSU1D/_VEGESU1 variables.
*/

{% macro brfss_times_per_day(column) %}
    case
        when cast({{ column }} as integer) between 101 and 199
            then cast({{ column }} as double) - 100
        when cast({{ column }} as integer) between 201 and 299
            then (cast({{ column }} as double) - 200) / 7.0
        when cast({{ column }} as integer) in (300, 555)
            then 0.0
        when cast({{ column }} as integer) between 301 and 399
            then (cast({{ column }} as double) - 300) / 30.0
        else null
    end
{% endmacro %}
