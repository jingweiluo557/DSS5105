"""Console-default entry points for the reminder event function."""
from timer import main_handler

# CloudBase defaults to index.main; SCF Python commonly uses index.main_handler.
main = main_handler
