export default [
  {
    files: ["web/static/**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "script",
      globals: {
        URLSearchParams: "readonly",
        console: "readonly",
        document: "readonly",
        fetch: "readonly",
        location: "readonly",
        window: "readonly",
      },
    },
    rules: {
      eqeqeq: "error",
      "no-undef": "error",
      "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "no-var": "error",
      "prefer-const": "error",
    },
  },
];
