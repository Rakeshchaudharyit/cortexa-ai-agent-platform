# Portfolio Release Checklist

## Repository
- [ ] `./scripts/release-preflight.sh` passes
- [ ] `make validate` passes locally
- [ ] no `.env` / `.env.production` / private files are tracked
- [ ] README screenshots/URLs are current
- [ ] GitHub CI is green

## Product
- [ ] public `/` and `/demo` work logged out
- [ ] login restores `/workspace`
- [ ] Document Knowledge answer returns valid citations
- [ ] evaluation run completes in the worker
- [ ] analytics and feedback review load
- [ ] background jobs dashboard reports worker healthy

## Deployment
- [ ] DNS resolves to the demo host
- [ ] HTTPS certificate is valid
- [ ] `/health` and `/ready` return successfully
- [ ] secure refresh cookie works after hard refresh
- [ ] database/document backups exist
- [ ] demo account contains only portfolio-safe data

## Portfolio
- [ ] GitHub repository description/topics configured
- [ ] live-demo URL added to GitHub
- [ ] 6–8 final screenshots captured
- [ ] 3–5 minute demo video recorded
- [ ] Upwork case study published
