@echo off
echo Running CVG GeoServ Processor tests...
python -m pytest tests/ -v --tb=short
pause
