"""Clean and merge the three assignment CSVs into an audited SQLite DB."""
from __future__ import annotations

import argparse, json, re, sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "naukri": ROOT / "data/source1_naukri_applicants.csv",
    "gig_workers": ROOT / "data/source2_gig_workers.csv",
    "cbnexus": ROOT / "data/source3_cbnexus_contacts.csv",
}
CITIES = {"bangalore":"Bengaluru", "bengaluru":"Bengaluru", "delhi":"Delhi NCR",
          "new delhi":"Delhi NCR", "delhi ncr":"Delhi NCR", "gurgaon":"Gurugram",
          "gurugram":"Gurugram", "noida":"Noida", "pune":"Pune"}
SCHEMAS = {
  "naukri": {
    "Full Name":["Candidate Name","Name"], "Email":["Email Address","email_id"],
    "Phone":["Phone Number","Mobile"], "City":["Location"],
    "Experience (Years)":["Experience","Years of Experience"], "Current CTC":["CTC"],
    "Applied Date":["Application Date"], "Skills":["Skill Tags"]},
  "gig_workers": {
    "email_id":["Email","Email Address"], "worker_name":["Worker Name","Name"],
    "rate":["Rate"], "location":["Location","City"], "status":["Status"],
    "skill_tags":["Skill Tags","Skills"]},
  "cbnexus": {
    "Name":["Full Name","Contact Name"], "Phone Number":["Phone","Mobile"],
    "City":["Location"], "Verified":["Is Verified"],
    "Projects Completed":["Completed Projects"]},
}

class SchemaError(ValueError):
    """Raised before database writing when an input file has unsafe columns."""

def read_source(path: Path, source: str) -> pd.DataFrame:
    if not path.exists():
        raise SchemaError(f"{source}: file not found: {path}")
    frame=pd.read_csv(path)
    # Match column aliases without caring about capitalization or outer spaces.
    available={str(column).strip().lower():column for column in frame.columns}
    rename={}
    missing=[]
    for canonical, aliases in SCHEMAS[source].items():
        found=next((available[name.lower()] for name in [canonical,*aliases] if name.lower() in available),None)
        if found is None: missing.append(canonical)
        else: rename[found]=canonical
    if missing:
        raise SchemaError(f"{source}: missing required columns: {', '.join(missing)}")
    return frame.rename(columns=rename)

def text(value: Any) -> str | None:
    if pd.isna(value): return None
    result = " ".join(str(value).strip().split())
    return result or None

def email(value: Any) -> str | None:
    value = text(value)
    if not value: return None
    value = value.lower()
    return value if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) else None

def phone(value: Any) -> str | None:
    value = text(value)
    digits = re.sub(r"\D", "", value or "")[-10:]
    return digits if len(digits) == 10 and digits[0] in "6789" else None

def city(value: Any) -> str | None:
    value = text(value)
    return CITIES.get(value.lower(), value.title()) if value else None

def date(value: Any) -> str | None:
    value = text(value)
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y"):
        try: return datetime.strptime(value or "", fmt).date().isoformat()
        except ValueError: pass
    return None

def ctc(value: Any) -> float | None:
    try: amount = float(value)
    except (TypeError, ValueError): return None
    return amount * 100_000 if amount < 100 else amount

def rate(value: Any) -> tuple[float | None, str | None]:
    match = re.fullmatch(r"([\d.]+)(k)?/(hr|month)", (text(value) or "").lower())
    if not match: return None, None
    amount = float(match.group(1)) * (1000 if match.group(2) else 1)
    return amount, "hour" if match.group(3) == "hr" else "month"

def skills(value: Any) -> list[str]:
    aliases = {"fastapi":"FastAPI", "javascript":"JavaScript", "langchain":"LangChain",
      "mongodb":"MongoDB", "mysql":"MySQL", "n8n":"n8n", "pandas":"Pandas",
      "react":"React", "rest apis":"REST APIs", "sql":"SQL", "web scraping":"Web Scraping"}
    return sorted({aliases.get(x.strip().lower(), x.strip().title())
                   for x in (text(value) or "").split(",") if x.strip()})

def base(source: str, row_number: int, raw: dict) -> dict:
    return {"source":source, "source_row":row_number, "raw_data":json.dumps(raw, default=str),
      "full_name":None, "email":None, "phone":None, "city":None, "experience_years":None,
      "current_ctc_annual":None, "rate_amount":None, "rate_period":None, "status":None,
      "skills":[], "projects_completed":None, "is_verified":None, "applied_date":None,
      "was_repaired":0}

def load_naukri(path: Path) -> tuple[list[dict], list[tuple]]:
    output=[]
    for i, raw in read_source(path,"naukri").iterrows():
        row=base("naukri", i+2, raw.to_dict())
        row.update(full_name=text(raw["Full Name"]).title(), email=email(raw.Email),
          phone=phone(raw.Phone), city=city(raw.City), experience_years=float(raw["Experience (Years)"]),
          current_ctc_annual=ctc(raw["Current CTC"]), applied_date=date(raw["Applied Date"]),
          skills=skills(raw.Skills))
        output.append(row)
    return output, []

def load_gig(path: Path) -> tuple[list[dict], list[tuple]]:
    output, rejected = [], []
    for i, series in read_source(path,"gig_workers").iterrows():
        n=i+2; raw=series.to_dict()
        if series.isna().all():
            rejected.append(("gig_workers", n, "completely blank row", json.dumps(raw, default=str))); continue
        repaired=0
        if not email(raw["email_id"]) and email(raw["worker_name"]):
            raw={"email_id":raw["worker_name"], "worker_name":raw["rate"], "rate":raw["location"],
                 "location":raw["status"], "status":raw["skill_tags"], "skill_tags":raw["email_id"]}
            repaired=1
        amount, period=rate(raw["rate"]); status=(text(raw["status"]) or "").lower()
        if not email(raw["email_id"]) or not text(raw["worker_name"]) or amount is None or status not in {"active","inactive","paused"}:
            rejected.append(("gig_workers", n, "invalid required fields", json.dumps(raw, default=str))); continue
        row=base("gig_workers", n, raw); row.update(full_name=text(raw["worker_name"]).title(),
          email=email(raw["email_id"]), city=city(raw["location"]), rate_amount=amount,
          rate_period=period, status=status, skills=skills(raw["skill_tags"]), was_repaired=repaired)
        output.append(row)
    return output, rejected

def load_cbnexus(path: Path) -> tuple[list[dict], list[tuple]]:
    output, rejected = [], []
    for i, raw in read_source(path,"cbnexus").iterrows():
        n=i+2; data=raw.to_dict()
        if text(raw.Name)=="Name" and text(raw["Phone Number"])=="Phone Number":
            rejected.append(("cbnexus", n, "repeated header row", json.dumps(data))); continue
        clean_phone=phone(raw["Phone Number"])
        if not clean_phone:
            rejected.append(("cbnexus", n, "invalid phone", json.dumps(data, default=str))); continue
        verified=(text(raw.Verified) or "").lower()
        verified_value=1 if verified in {"y","yes","verified"} else 0 if verified in {"n","no"} else None
        row=base("cbnexus", n, data); row.update(full_name=text(raw.Name).title(), phone=clean_phone,
          city=city(raw.City), projects_completed=int(raw["Projects Completed"]), is_verified=verified_value)
        output.append(row)
    return output, rejected

class UnionFind:
    def __init__(self, size: int): self.parent=list(range(size))
    def find(self, x: int) -> int:
        if self.parent[x] != x: self.parent[x]=self.find(self.parent[x])
        return self.parent[x]
    def union(self, a: int, b: int):
        a,b=self.find(a),self.find(b)
        if a != b: self.parent[b]=a

def merge(rows: list[dict]) -> list[dict]:
    uf=UnionFind(len(rows)); seen={}
    # A name + city key is unsafe when it occurs twice in the same source:
    # those may be two different people who happen to share a name and city.
    name_city_sources={}
    for row in rows:
        if row["full_name"] and row["city"] and "." not in row["full_name"]:
            key=(row["full_name"].lower(),row["city"])
            counts=name_city_sources.setdefault(key,{})
            counts[row["source"]]=counts.get(row["source"],0)+1
    for i,row in enumerate(rows):
        keys=[]
        if row["email"]: keys.append(("email",row["email"]))
        if row["phone"]: keys.append(("phone",row["phone"]))
        if row["full_name"] and row["city"] and "." not in row["full_name"]:
            name_city=(row["full_name"].lower(),row["city"])
            if max(name_city_sources[name_city].values()) == 1:
                keys.append(("name_city",*name_city))
        for key in keys:
            if key in seen: uf.union(i,seen[key])
            else: seen[key]=i
    groups={}
    for i,row in enumerate(rows): groups.setdefault(uf.find(i),[]).append(row)
    fields=["full_name","email","phone","city","experience_years","current_ctc_annual",
            "rate_amount","rate_period","status","projects_completed","is_verified","applied_date"]
    result=[]
    for group in groups.values():
        candidate={field:next((r[field] for r in group if r[field] is not None),None) for field in fields}
        candidate.update(skills=", ".join(sorted({s for r in group for s in r["skills"]})) or None,
          data_sources=", ".join(sorted({r["source"] for r in group})), source_row_count=len(group), _rows=group)
        result.append(candidate)
    return result

def write_db(path: Path, candidates: list[dict], rejected: list[tuple]):
    with sqlite3.connect(path) as db:
        db.executescript("""
        DROP TABLE IF EXISTS candidate_sources; DROP TABLE IF EXISTS rejected_rows; DROP TABLE IF EXISTS candidates;
        CREATE TABLE candidates (id INTEGER PRIMARY KEY, full_name TEXT NOT NULL, email TEXT, phone TEXT,
          city TEXT, experience_years REAL, current_ctc_annual REAL, rate_amount REAL, rate_period TEXT,
          status TEXT, skills TEXT, projects_completed INTEGER, is_verified INTEGER, applied_date TEXT,
          data_sources TEXT NOT NULL, source_row_count INTEGER NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE candidate_sources (id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL REFERENCES candidates(id),
          source TEXT, source_row INTEGER, raw_data TEXT, was_repaired INTEGER);
        CREATE TABLE rejected_rows (id INTEGER PRIMARY KEY, source TEXT, source_row INTEGER, reason TEXT, raw_data TEXT);
        CREATE INDEX idx_candidates_email ON candidates(email); CREATE INDEX idx_candidates_phone ON candidates(phone);
        """)
        fields=[k for k in candidates[0] if not k.startswith("_")]; marks=", ".join("?" for _ in fields)
        for candidate in candidates:
            cursor=db.execute(f"INSERT INTO candidates ({', '.join(fields)}) VALUES ({marks})",[candidate[k] for k in fields])
            db.executemany("INSERT INTO candidate_sources (candidate_id,source,source_row,raw_data,was_repaired) VALUES (?,?,?,?,?)",
              [(cursor.lastrowid,r["source"],r["source_row"],r["raw_data"],r["was_repaired"]) for r in candidate["_rows"]])
        db.executemany("INSERT INTO rejected_rows (source,source_row,reason,raw_data) VALUES (?,?,?,?)",rejected)

def run(files: dict[str,Path], database: Path) -> dict[str,int]:
    rows=[]; rejected=[]
    for source, loader in (("naukri",load_naukri),("gig_workers",load_gig),("cbnexus",load_cbnexus)):
        accepted,bad=loader(files[source]); rows.extend(accepted); rejected.extend(bad)
    candidates=merge(rows); write_db(database,candidates,rejected)
    return {"raw rows":sum(len(pd.read_csv(p)) for p in files.values()), "accepted rows":len(rows),
      "repaired rows":sum(r["was_repaired"] for r in rows), "rejected rows":len(rejected),
      "unique candidates":len(candidates), "duplicates merged":len(rows)-len(candidates)}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database",type=Path,default=ROOT/"consultbae.db")
    parser.add_argument("--naukri",type=Path,default=FILES["naukri"])
    parser.add_argument("--gig-workers",type=Path,default=FILES["gig_workers"])
    parser.add_argument("--cbnexus",type=Path,default=FILES["cbnexus"])
    args=parser.parse_args()
    selected={"naukri":args.naukri,"gig_workers":args.gig_workers,"cbnexus":args.cbnexus}
    try: summary=run(selected,args.database)
    except SchemaError as error: parser.error(str(error))
    print("\nConsultBae ingestion completed")
    for label,value in summary.items(): print(f"  {label.title():20} {value}")
    print(f"\nDatabase: {args.database}")

if __name__ == "__main__": main()
