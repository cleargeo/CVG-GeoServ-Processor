# Contributing — CVG GeoServ Processor

© Clearview Geographic, LLC — Internal Use Only

## Development Setup

```bash
git clone <repo>
cd CVG_GeoServ_Processor
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
# or
run_tests.bat
```

## Code Style

- Black formatter: `black geoserv_processor/`
- Flake8 lint: `flake8 geoserv_processor/`
- Max line length: 100
- All public functions must have docstrings
- Type hints required on all function signatures

## Adding a New Operation

1. Create `geoserv_processor/ops/my_op.py` with a `run_my_op(job: JobConfig) -> str` function
2. Add config dataclass to `config.py` (e.g., `MyOpConfig`)
3. Add `"my_op"` to `VALID_OPS` in `config.py`
4. Add `MyOpConfig` field to `JobConfig.from_dict()`
5. Register in `processing.py` `_register_ops()`
6. Import in `ops/__init__.py`
7. Document in `list-ops` command in `cli.py`
8. Add test to `tests/test_ops.py`

## Pattern Reference

Follow the exact module/docstring/header pattern of existing CVG wizard packages:
- `storm_surge_wizard` (SSW v1.4.1) 
- `slr_wizard` (SLR v1.1.0)
- `rainfall_wizard` (Rainfall v1.x)
