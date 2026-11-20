// The feature-request footer closing every detail panel, like the loading screen's
// call to action: a one-line invitation, then the repo's issue tracker (only when
// the deployment configures a repo, see web-url.js issuesUrl) and the contact page.
// Its /api/ Markdown twin is llms_txt.FEEDBACK: keep the wording in step.

import { el } from "./dom.js";
import { configIssuesUrl } from "../web-url.js";

const { t } = window.__I18N__;

const link = (href, label) => {
  const a = el("a", null, label);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
};

/** The footer element: "Have an idea ...: open a GitHub issue or email me." */
export function feedbackFooter() {
  const p = el("p", "info-feedback", `${t("panel.feedback")} `);
  const issues = configIssuesUrl();
  if (issues) {
    p.appendChild(link(issues, t("panel.feedbackIssue")));
    p.appendChild(document.createTextNode(` ${t("panel.feedbackOr")} `));
  }
  p.appendChild(link(t("panel.contactUrl"), t("panel.feedbackEmail")));
  p.appendChild(document.createTextNode("."));
  return p;
}
