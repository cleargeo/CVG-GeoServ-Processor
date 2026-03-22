@echo off
echo Starting CVG GeoServ Processor (dev mode)...
python -m geoserv_processor.cli web --host 0.0.0.0 --port 8003 --reload
pause
