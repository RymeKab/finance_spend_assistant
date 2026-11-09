# Shortcuts. Each target runs the same commands the README lists.
# (On Windows without `make`, run the commands from the README directly.)

.PHONY: install backend frontend test

install:            ## install backend and frontend dependencies
	cd backend && python -m pip install -r requirements.txt
	cd frontend && npm install

backend:            ## start the API on http://localhost:8000
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:           ## start the UI on http://localhost:5173
	cd frontend && npm run dev

test:               ## run the backend test suite
	cd backend && pytest
