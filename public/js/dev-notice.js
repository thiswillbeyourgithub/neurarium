// Optional "work in progress" popup (#dev-modal), shown once per page load.
//
// When the container is started with DEV=1 (docker/.env -> entrypoint.sh ->
// /gen/app-config.js), this tells visitors the site is actively (re)deployed: how long
// ago the container last restarted, plus a "stay tuned / come back later" note and an
// optional Source link. STARTED_AT (epoch seconds) is stamped by the entrypoint at
// container start.
//
// Off entirely unless DEV resolved to the literal "1": empty, "0" or the leftover
// "{{...}}" placeholder (local dev served without templating) all keep it hidden, so
// production looks normal unless explicitly enabled. The dismissal is NOT remembered:
// while DEV=1 every load should say so.
//
// The viewer shows it after the loading screen and before "What's new"
// (js/boot/launch.js chains the two); the drugs map page, which has neither, shows it
// on boot (js/drugs-map-main.js).

import { wireModal } from "./about/modals.js";

const { t } = window.__I18N__;

/**
 * Human "X minutes/hours/days" from a count of elapsed seconds, in the coarsest
 * sensible unit. Negative (skewed clocks) reads as "less than a minute".
 * @param {number} seconds
 * @returns {string}
 */
export function humanAgo(seconds) {
  const minutes = Math.max(0, Math.round(seconds / 60));
  if (minutes < 1) return t("time.lessThanMinute");
  if (minutes < 60) return t("time.minutes", { n: minutes, s: minutes === 1 ? "" : "s" });
  const hours = Math.round(minutes / 60);
  if (hours < 24) return t("time.hours", { n: hours, s: hours === 1 ? "" : "s" });
  const days = Math.round(hours / 24);
  return t("time.days", { n: days, s: days === 1 ? "" : "s" });
}

/** The popup's body, built as DOM nodes (never innerHTML) so neither the configured
 * URL nor a translation can inject markup. */
function fillBody(body, cfg) {
  const startedAt = Number(cfg.startedAt);
  const when = Number.isFinite(startedAt) && startedAt > 0
    ? t("dev.restarted", { ago: humanAgo(Date.now() / 1000 - startedAt) })
    : t("dev.activelyDeveloped");
  const p = document.createElement("p");
  p.textContent = `${when}${t("dev.stayTuned")}`;
  body.replaceChildren(p);
  const sourceUrl = String(cfg.sourceUrl || "").trim();
  if (/^https?:\/\//i.test(sourceUrl)) {
    const a = document.createElement("a");
    a.href = sourceUrl;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = t("dev.source");
    const line = document.createElement("p");
    line.append(a);
    body.append(line);
  }
}

/**
 * Show the WIP popup when DEV=1, resolving once it is closed (immediately when the
 * popup is off or its markup is absent), so a caller can chain the next popup.
 * @returns {Promise<void>}
 */
export function showDevNotice() {
  const cfg = window.__APP_CONFIG__ || {};
  const modal = document.getElementById("dev-modal");
  const body = document.getElementById("dev-body");
  if (cfg.dev !== "1" || !modal || !body) return Promise.resolve();
  const version = window.__APP_VERSION__ ? ` (v${window.__APP_VERSION__})` : "";
  document.getElementById("dev-title").textContent = `${t("dev.wip")}${version}`;
  fillBody(body, cfg);
  return new Promise((resolve) => {
    // The viewer's Esc router (js/boot/shortcuts.js) knows only its own popups, so
    // this one takes Esc itself, ahead of it (capture phase).
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      e.stopImmediatePropagation();
      e.preventDefault();
      ctrl.close();
    };
    const done = new MutationObserver(() => {
      if (!modal.hidden) return;
      done.disconnect();
      window.removeEventListener("keydown", onKey, true);
      resolve();
    });
    const ctrl = wireModal({ modalId: "dev-modal", closeId: "dev-close" });
    window.addEventListener("keydown", onKey, true);
    ctrl.open();
    done.observe(modal, { attributes: true, attributeFilter: ["hidden"] });
  });
}
