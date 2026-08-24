import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // Every data panel here follows the same shape: an effect keyed on
      // `refreshKey` that sets a loading flag, fetches, then stores the
      // result. That trips this rule by design -- the setState is the
      // request's own lifecycle, not state derived from props that should
      // have been computed during render, which is what the rule is really
      // aimed at. Downgraded to a warning rather than disabled, so a genuine
      // cascading-render mistake still shows up in output, and kept as a
      // deliberate project-wide decision rather than eight scattered
      // eslint-disable comments.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
