# One-command entry points for the platform. `make help` lists them.
# Requires: Docker (for the stack), a JDK + Maven wrapper, Node, and Python for the test targets.

.DEFAULT_GOAL := help
UI  := http://localhost:8088
API := http://localhost:8080

.PHONY: help
help: ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---- the demo -----------------------------------------------------------------
.PHONY: demo
demo: up wait ## Bring up the whole stack and show data flowing across the services
	@echo ""
	@echo "── Fixed-income desk (backend) ─────────────────────────────"
	@curl -s $(UI)/api/securities | head -c 400; echo " ..."
	@echo ""
	@echo "── Order blotter ───────────────────────────────────────────"
	@curl -s "$(UI)/api/orders" | head -c 400; echo " ..."
	@echo ""
	@echo "── Desk risk (aggregated from the Kafka event stream) ──────"
	@curl -s http://localhost:8081/api/risk/summary || true
	@echo ""
	@echo ""
	@echo "The exchange simulation and strategy runners generate live order flow;"
	@echo "watch it in the UI and in Grafana:"
	@echo "  UI          $(UI)"
	@echo "  Exchange    $(UI)/exchange"
	@echo "  Grafana     http://localhost:3000   (admin/admin)"
	@echo "  Prometheus  http://localhost:9090"
	@echo ""
	@echo "Tear down with:  make down"

.PHONY: wait
wait: ## Wait for the API (via the UI proxy) to be ready
	@echo "Waiting for the stack to come up ..."
	@for i in $$(seq 1 60); do \
		curl -sf $(UI)/api/securities >/dev/null 2>&1 && { echo "ready."; exit 0; }; \
		sleep 5; \
	done; \
	echo "Stack did not come up in time; try 'docker compose logs'"; exit 1

# ---- stack lifecycle ----------------------------------------------------------
.PHONY: up
up: ## Build and start the full stack (detached)
	docker compose up --build -d

.PHONY: down
down: ## Stop the stack and remove volumes
	docker compose down -v

.PHONY: logs
logs: ## Tail the stack logs
	docker compose logs -f --tail=100

# ---- tests --------------------------------------------------------------------
.PHONY: test
test: test-backend test-risk test-frontend test-research test-harness ## Run every test suite

.PHONY: test-backend
test-backend: ## Backend tests (needs Docker for integration tests)
	cd backend && ./mvnw -B verify

.PHONY: test-risk
test-risk: ## Risk-service tests
	cd risk-service && ./mvnw -B verify

.PHONY: test-frontend
test-frontend: ## Frontend unit tests + build
	cd frontend && npm ci && npm test && npm run build

.PHONY: test-research
test-research: ## Quant research + alpha DSL tests
	cd research && python -m pytest -q

.PHONY: test-harness
test-harness: ## Validation harness tests + the example suite
	python -m pytest harness -q
	python -m harness --check-determinism

# ---- validation lab -----------------------------------------------------------
.PHONY: harness
harness: ## Run the validation harness (sealed, with repro bundles)
	python -m harness --out artifacts --seal --repro-dir repro

.PHONY: loadtest
loadtest: ## Matching-path load test: throughput + tail latency under concurrent load (thread sweep)
	cd backend && ./mvnw -q -B test-compile && \
		java -cp target/test-classes:target/classes com.bonddesk.exchange.OrderPathLoadTest 2000 16
