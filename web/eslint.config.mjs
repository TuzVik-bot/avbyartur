import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTypescript,
  {
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // Lint debt: the codebase was never linted. These rules fired as errors
      // when ESLint was introduced (2026-11-10) and are kept visible as warnings
      // until burned down; restore "error" once each count reaches zero.
      "react-hooks/set-state-in-effect": "warn", // 37 at introduction
      "react/no-children-prop": "warn", // 16 at introduction
      "@next/next/no-html-link-for-pages": "warn", // 3 at introduction
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "coverage/**",
    "test-results/**",
    "playwright-report/**",
    "next-env.d.ts",
    "src/lib/types.generated.ts",
  ]),
]);

export default eslintConfig;
