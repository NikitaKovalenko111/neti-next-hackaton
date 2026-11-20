package main

import (
	"log"
	"university-agent/internal/app"
	"university-agent/internal/config"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatal(err)
	}
	if err := app.Run(cfg); err != nil {
		log.Fatal(err)
	}
}
