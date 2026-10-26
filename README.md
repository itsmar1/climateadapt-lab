# ClimateAdapt Lab

Evidence-grounded AI agent for agricultural drought adaptation (Meta Global Developer AI
Hackathon project). **Status: Milestone 0** - repository foundation and a tested prototype
rainfall-anomaly endpoint.

## Scientific scope and limitations

- The only indicator so far is a simple precipitation **percentage anomaly**:
  `((observed_total - baseline_mean) / baseline_mean) * 100`.
- It is a prototype, **not** a calibrated drought index, and must not be used alone to
  classify drought severity. SPI and other validated indicators come in Milestone 2.
- No real datasets are used. Inputs are supplied by the caller and tagged with
  `data_origin` (`synthetic_example` or `user_supplied`).
- No global validation is claimed for anything in this repository.

## Setup (run from the repository root)

```bash
python3.11 -m venv .venv            # use `py -3.11 -m venv .venv` on Windows
source .venv/bin/activate           # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env                # Windows: copy .env.example .env
```

## Run the tests

```bash
pytest
```

## Run the API

```bash
uvicorn climateadapt.api.main:app --reload
```

Interactive docs: http://127.0.0.1:8000/docs

```bash
curl http://127.0.0.1:8000/health

curl -X POST http://127.0.0.1:8000/v1/analysis/rainfall-anomaly \
  -H "Content-Type: application/json" \
  -d '{"observed_total_mm": 80, "baseline_mean_mm": 100, "data_origin": "synthetic_example"}'
```

## Lint

```bash
ruff check .
```

## Error behaviour

| Situation | Result |
|---|---|
| Negative, non-finite (NaN/Infinity), non-numeric, or boolean precipitation | HTTP 422 |
| Missing/unknown fields, bad coordinates, end date before start date | HTTP 422 |
| Baseline of 0 mm | HTTP 200 with `status: "undefined"` and `percentage_anomaly: null` |