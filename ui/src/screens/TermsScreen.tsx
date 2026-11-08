// Disclaimer and terms (issue 219), at ?terms=1. Static: no API call, so it renders the
// same in the full and demo profiles. The text is in content/terms.ts.
import { TERMS, TERMS_TITLE } from "../content/terms";
import "./screens.css";

export function TermsScreen() {
  return (
    <article className="rd-terms" aria-labelledby="rd-terms-title">
      <h1 id="rd-terms-title">{TERMS_TITLE}</h1>
      <p className="rd-terms-updated">Last updated {TERMS.updated}</p>
      {TERMS.sections.map((section) => (
        <section key={section.heading}>
          <h2>{section.heading}</h2>
          {section.paragraphs.map((text) => (
            <p key={text}>{text}</p>
          ))}
        </section>
      ))}
    </article>
  );
}
