# React dashboard - build the static bundle, serve it with nginx.
#
# Build context is the REPO ROOT so we can copy both ui/ and ui/nginx.conf.
# VITE_AGENT_BASE is baked at BUILD time: it's the URL the operator's BROWSER
# uses to reach the agent (its published host port), not an internal compose
# name. Default matches the agent-server port mapping.
FROM node:22-slim AS build
WORKDIR /ui

ARG VITE_AGENT_BASE=http://localhost:8765
ENV VITE_AGENT_BASE=$VITE_AGENT_BASE

# pnpm 9 matches the repo's lockfileVersion 9.0. glibc base (not alpine)
# sidesteps rollup/esbuild musl optional-dep pitfalls.
RUN npm install -g pnpm@9

COPY ui/package.json ui/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY ui/ ./
RUN pnpm build

FROM nginx:alpine
COPY ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /ui/dist /usr/share/nginx/html
EXPOSE 80
