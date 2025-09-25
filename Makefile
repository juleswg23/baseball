# Variables
EXPORT_DIR = docs

.PHONY: all clean exp run

all: exp

exp:
	shinylive export shiny-app $(EXPORT_DIR)/

clean:
	rm -rf $(EXPORT_DIR)

run:
	python3 -m http.server --directory docs --bind localhost 8008