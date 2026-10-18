"""
Clean the BC Surgical Wait Times quarterly file for analysis in Power BI / SQL.

Source: BC Ministry of Health, "BC Surgical Wait Times" (BC Data Catalogue)
https://catalogue.data.gov.bc.ca/dataset/bc-surgical-wait-times

What this script does
1. Standardizes column names and trims text.
2. Converts suppressed "<5" counts to blanks and flags them (privacy suppression).
3. Builds real dates from fiscal year + quarter (BC fiscal Q1 = Apr-Jun).
4. Labels each row's aggregation level so totals are never double counted:
     province         -> All Health Authorities / All Facilities
     health_authority -> one authority / All Facilities
     hospital         -> one hospital
   and flags the "All Procedures" rollup rows.
5. Runs validation checks and writes clean CSVs.

NOTE: Wait-time percentiles cannot be averaged or summed across rows.
Use the pre-calculated rows at the level you need (that is why the
source provides them at every level).

Usage:
    python clean_wait_times.py path/to/quarterly_file.xlsx [output_dir]
"""

import sys
from pathlib import Path

import pandas as pd

QUARTER_START_MONTH = {"Q1": 4, "Q2": 7, "Q3": 10, "Q4": 1}


def load(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].str.strip()
    return df


def clean_counts(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["waiting", "completed"]:
        df[f"{col}_suppressed"] = df[col].eq("<5")
        df[col] = pd.to_numeric(df[col].where(~df[f"{col}_suppressed"]), errors="coerce").astype("Int64")
    for col in ["percentile_comp_50th", "percentile_comp_90th"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.rename(columns={"percentile_comp_50th": "median_wait_weeks",
                            "percentile_comp_90th": "p90_wait_weeks"})
    df["has_wait_times"] = df["median_wait_weeks"].notna()
    return df


def add_dates(df: pd.DataFrame) -> pd.DataFrame:
    # "2024/25" -> fiscal year starts April 2024
    df["fiscal_year_start"] = df["fiscal_year"].str[:4].astype(int)
    month = df["quarter"].map(QUARTER_START_MONTH)
    year = df["fiscal_year_start"] + (df["quarter"] == "Q4").astype(int)  # Q4 = Jan-Mar of next calendar year
    df["quarter_start"] = pd.to_datetime(dict(year=year, month=month, day=1))
    df["period_label"] = df["fiscal_year"] + " " + df["quarter"]
    return df


def add_levels(df: pd.DataFrame) -> pd.DataFrame:
    ha_total = df["health_authority"].eq("All Health Authorities")
    fac_total = df["hospital_name"].eq("All Facilities")
    df["level"] = "hospital"
    df.loc[fac_total, "level"] = "health_authority"
    df.loc[ha_total & fac_total, "level"] = "province"
    df["is_all_procedures"] = df["procedure_group"].eq("All Procedures")
    return df


def validate(df: pd.DataFrame) -> None:
    key = ["fiscal_year", "quarter", "health_authority", "hospital_name", "procedure_group"]
    dupes = df.duplicated(key).sum()
    assert dupes == 0, f"{dupes} duplicate rows on {key}"
    assert df["quarter"].isin(QUARTER_START_MONTH).all(), "unexpected quarter values"
    bad = df[(df["median_wait_weeks"] > df["p90_wait_weeks"])]
    assert bad.empty, f"{len(bad)} rows where median > 90th percentile"

    print("Rows:", len(df))
    print("Periods:", df["period_label"].iloc[0], "to", df.sort_values("quarter_start")["period_label"].iloc[-1])
    print("Rows by level:\n", df["level"].value_counts().to_string())
    print("Suppressed waiting:", int(df["waiting_suppressed"].sum()),
          "| suppressed completed:", int(df["completed_suppressed"].sum()),
          "| rows without wait times:", int((~df["has_wait_times"]).sum()))

    # Check: hospital rows should roughly add up to the health authority total.
    # (Won't match exactly because suppressed "<5" values are blank.)
    hosp = df[(df.level == "hospital") & df.is_all_procedures].groupby(
        ["fiscal_year", "quarter", "health_authority"])["completed"].sum()
    ha = df[(df.level == "health_authority") & df.is_all_procedures].set_index(
        ["fiscal_year", "quarter", "health_authority"])["completed"]
    gap = (ha - hosp).dropna()
    print("HA total minus sum of hospitals (completed, all procedures): "
          f"median {gap.median():.0f}, max {gap.max():.0f}  (small gaps = suppressed cells)")


def main() -> None:
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    out.mkdir(parents=True, exist_ok=True)

    df = add_levels(add_dates(clean_counts(load(src))))
    validate(df)

    cols = ["fiscal_year", "quarter", "period_label", "quarter_start", "fiscal_year_start",
            "level", "health_authority", "hospital_name", "procedure_group", "is_all_procedures",
            "waiting", "completed", "median_wait_weeks", "p90_wait_weeks",
            "waiting_suppressed", "completed_suppressed", "has_wait_times"]
    df = df[cols].sort_values(["quarter_start", "level", "health_authority", "hospital_name", "procedure_group"])

    df.to_csv(out / "wait_times_clean.csv", index=False)
    for lvl in ["province", "health_authority", "hospital"]:
        df[df.level == lvl].to_csv(out / f"wait_times_{lvl}.csv", index=False)
    print("Wrote CSVs to", out.resolve())


if __name__ == "__main__":
    main()
