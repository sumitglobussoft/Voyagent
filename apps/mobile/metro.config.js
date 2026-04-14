// Expo + Metro config for the Voyagent monorepo.
//
// Enables workspace symlink resolution and package-exports support so
// Metro can resolve `@voyagent/*` workspace packages the same way Node /
// the web / desktop builds do.
const { getDefaultConfig } = require("expo/metro-config");
const path = require("node:path");

const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, "../..");

const config = getDefaultConfig(projectRoot);

// Watch the whole workspace so Metro picks up changes in @voyagent/* packages.
config.watchFolders = [workspaceRoot];

// Prefer deeper node_modules resolution; Metro walks up from project root.
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, "node_modules"),
  path.resolve(workspaceRoot, "node_modules"),
];

// pnpm's hoisted layout uses symlinks heavily — these two flags make Metro
// follow them and respect package `exports` maps.
config.resolver.unstable_enableSymlinks = true;
config.resolver.unstable_enablePackageExports = true;

module.exports = config;
