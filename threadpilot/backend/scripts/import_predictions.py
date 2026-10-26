"""Import the audited forecast asset without loading executable pickle models."""
from app.config import Settings
from app.db.session import Database
from app.forecast_store import import_forecasts
from app.services.dashboard_service import forecast_asset

if __name__ == '__main__':
    db=Database(Settings())
    try:
        result=import_forecasts(db,forecast_asset())
        print(f"Imported {result['rows']} predictions in batch {result['batch_id'][:12]}.")
    finally:
        db.close()
