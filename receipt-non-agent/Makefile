.PHONY: run test-local lint format typecheck install docker-build docker-run clean

run:
	python main.py

test-local:
	python test_local.py $(IMG)

lint:
	ruff check .

format:
	ruff format .

typecheck:
	pyright

install:
	pip install -r requirements.txt
	pip install ruff pyright

docker-build:
	docker build -t reimbursement-agent .

docker-run:
	docker run -p 8000:8000 --env-file .env reimbursement-agent

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf receipts/*.jpg receipts/*.png receipts/*.webp
