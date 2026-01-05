include .env

ifeq ($(ENV),dev)
    COMPOSE_ARGS = -f docker-compose.yml -f docker-compose.dev.yml
else
    COMPOSE_ARGS = -f docker-compose.yml
endif

COMPOSE_BAKE = true

default: up logs

build:
	@echo "Building images..."
	COMPOSE_BAKE=$(COMPOSE_BAKE) $(DOCKER_TOOL) compose -p $(PROJECT_NAME) $(COMPOSE_ARGS) build

up: down build
	@echo "Starting containers..."
	$(DOCKER_TOOL) compose -p $(PROJECT_NAME) $(COMPOSE_ARGS) up -d

down:
	@echo "Stopping and removing containers..."
	$(DOCKER_TOOL) compose -p $(PROJECT_NAME) $(COMPOSE_ARGS) down

logs:
	@echo "Tailing logs for $(SERVICE_NAME)..."
	$(DOCKER_TOOL) compose -p $(PROJECT_NAME) $(COMPOSE_ARGS) logs -f

restart: down up

watch:
	@echo "Watching for file changes and restarting containers..."
	while inotifywait -r -e modify,create,delete ./; do \
		$(MAKE) restart; \
	done

clean: down
	@echo "Removing images and volumes..."
	$(DOCKER_TOOL) compose -p $(PROJECT_NAME) $(COMPOSE_ARGS) down --rmi all --volumes
