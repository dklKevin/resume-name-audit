# Name selection

The 12 names in `materials/names.csv` come from the validated names data of Crabtree, Gaddis, Holbein and Larsen (2023), "Validated names for experimental studies on race and ethnicity", Scientific Data 10, 130.
Each of the 600 names was rated by US survey respondents on perceived race, income, education and citizenship.

## Source files

- `crabtree2023_full_data.json` is a copy of `web-app/data/full_data.json` from the name selector's repository, [jaeyk/select_validated_names](https://github.com/jaeyk/select_validated_names), at commit `28f656c80c86d762c7d97e62645d89d6c4ed5c38` (2026-02-07).
  That repository builds the file in `data_prep/download_data.R` from the paper's Harvard Dataverse files ([doi:10.7910/DVN/LP4EAR](https://doi.org/10.7910/DVN/LP4EAR)): the pooled survey responses and `names.rds`.
- Fields used: `identity` (the race the name was built to signal), `mean_correct` (share of respondents who assigned the name to that race), `avg_income` and `avg_education` (mean ordinal ratings of perceived income and education), `avg_citizenship` (share who rated the person a citizen).
- `ssa_first_name_sex.csv` gives, for every first name in the Black and white groups, the number of US births recorded as female and male in Social Security baby name data for 1880 to 2017, as packaged in the [hadley/babynames](https://github.com/hadley/babynames) R package.
  `scripts/ssa_first_name_sex.py` rebuilds it.
  The validated names data does not rate gender, so this is the gender check.

## Rules

`scripts/select_names.py` applies these rules in order and writes `materials/names.csv`.

1. Groups: identity "Black or African American" is Black, "White" is white.
2. Gender: a first name is female when at least 90 percent of its SSA births are female and male when at most 10 percent are; anything in between is dropped.
3. Drop the first names in the title of Bertrand and Mullainathan (2004), the most repeated audit study names: Emily, Greg, Lakisha, Jamal.
4. Keep names that at least two thirds of respondents assigned to the intended race.
5. Within a group, the three names have distinct surnames and use as many distinct first names as the eligible pool allows.
6. Class match: each group's mean perceived income and mean perceived education must be within 0.10 of every other group's.
   Among the sets that satisfy that, pick the one whose weakest group has the highest mean correct identification, then the highest overall.
7. The degree swap uses the name with the highest correct identification in each group.

## Result

| group | name | correct | income | education | citizen | degree swap |
|---|---|---|---|---|---|---|
| Black F | Tamika Jackson | 0.864 | 1.881 | 2.051 | 0.966 | yes |
| Black F | Latonya Williams | 0.809 | 1.838 | 1.882 | 0.941 | |
| Black F | Latasha Burke | 0.806 | 1.806 | 1.902 | 0.919 | |
| Black M | Jermaine Wood | 0.746 | 1.778 | 1.762 | 0.984 | yes |
| Black M | Jermaine Jackson | 0.742 | 1.879 | 1.955 | 0.955 | |
| Black M | Darnell Williams | 0.692 | 1.877 | 2.031 | 0.954 | |
| white F | Mary Meyer | 0.911 | 1.822 | 1.911 | 0.978 | yes |
| white F | Mary Ryan | 0.884 | 1.904 | 1.926 | 0.979 | |
| white F | Mary Snyder | 0.848 | 1.884 | 1.964 | 0.946 | |
| white M | Thomas Snyder | 0.905 | 1.941 | 2.060 | 0.976 | yes |
| white M | David Ryan | 0.886 | 1.943 | 2.000 | 0.971 | |
| white M | Michael Meyer | 0.816 | 1.913 | 1.951 | 0.961 | |

Group means: correct identification 0.827, 0.727, 0.881 and 0.869; perceived income 1.842, 1.845, 1.870 and 1.932; perceived education 1.945, 1.916, 1.934 and 2.004 (Black F, Black M, white F, white M).

## Limits of the pool

- The only white female first name in the data is Mary, so the three white female names share a first name and differ only by surname.
- The only Black male first names identified by at least two thirds of respondents are Jermaine and Darnell, so two of the three Black male names share a first name.
- Most Black first names in the data (Tamika, Latonya, Jermaine, Darnell and others) also appear in the 2004 audit study's longer name list.
  Excluding all of them would leave no usable Black male name, so only the four title names are excluded.
- Darnell is 92 percent male in SSA births, which passes the 90 percent rule but is the least clear cut first name in the set.
