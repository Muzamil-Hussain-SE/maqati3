import coreWebVitals from 'eslint-config-next/core-web-vitals';
import typescript from 'eslint-config-next/typescript';

/*
 * Arabic is a first-class language here, not an afterthought, so the layout is written
 * in logical properties throughout. A physical `ml-4` that looks right in English puts
 * the margin on the wrong side in Arabic, and nobody who only reads English will ever
 * notice. This rule is what stops that reaching production.
 */
const PHYSICAL = String.raw`(^|[\s])(-?(ml|mr|pl|pr|left|right|border-l|border-r|rounded-l|rounded-r|rounded-tl|rounded-tr|rounded-bl|rounded-br|inset-l|inset-r)-|text-(left|right)($|[\s]))`;

const MESSAGE =
  'Use logical properties, not physical ones: ms-/me-/ps-/pe-/start-/end-/border-s/border-e/text-start/text-end. Physical sides break Arabic (RTL) silently.';

export default [
  ...coreWebVitals,
  ...typescript,
  {
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: `JSXAttribute[name.name='className'] Literal[value=/${PHYSICAL}/]`,
          message: MESSAGE,
        },
        {
          selector: `JSXAttribute[name.name='className'] TemplateElement[value.raw=/${PHYSICAL}/]`,
          message: MESSAGE,
        },
      ],
    },
  },
  { ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts'] },
];
