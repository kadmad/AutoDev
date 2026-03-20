from fastapi import APIRouter

from app.api.v1 import setup, users, projects, pipelines, plans, tests, gitlab, zoho, github

api_router = APIRouter()

# Auth & setup
api_router.include_router(setup.router, tags=["auth"])

# Users
api_router.include_router(users.router, tags=["users"])

# Projects
api_router.include_router(projects.router, tags=["projects"])

# Pipelines
api_router.include_router(pipelines.router, tags=["pipelines"])

# Plan review
api_router.include_router(plans.router, tags=["plans"])

# Test results
api_router.include_router(tests.router, tags=["tests"])

# GitLab / MR
api_router.include_router(gitlab.router, tags=["gitlab"])

# Zoho webhook
api_router.include_router(zoho.router, tags=["zoho"])

# GitHub OAuth
api_router.include_router(github.router, tags=["github"])

