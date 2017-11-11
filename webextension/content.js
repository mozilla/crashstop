/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

"use strict";

const selector = document.getElementById("cf_crash_signature_edit_container") ? "cf_crash_signature_edit_container" : "field-value-cf_crash_signature";
const container = document.getElementById(selector);
if (container) {
    const signatures = [];
    document.querySelectorAll("#" + selector + " a").forEach(a => {
        let s = a.innerText.trim();
        const obat = s.startsWith("[@");
        const cb = s.endsWith("]");
        if (obat) {
            s = cb ? s.slice(2, -1) : s.slice(2);
            s = s.trim();
        } else if (cb) {
            s = s.slice(-1).trim();
        }
        signatures.push("s=" + s);
    });
    if (signatures) {
        const hgurlPattern = new RegExp("^http[s]?://hg\.mozilla\.org/(?:releases/)?mozilla-([^/]*)/rev/([0-9a-f]+)$");
        const repos = new Set(["central", "beta", "release"]);
        const hgurls = [];
        let isFirst = false;
        document.querySelectorAll(".comment-text > a").forEach(a => {
            const prev = a.previousSibling;
            if (prev == null || (prev.previousSibling == null && !prev.textContent.trim())) {
                isFirst = true;
            }
            if (isFirst) {
                const link = a.href;
                const m = link.match(hgurlPattern);
                if (m != null) {
                    let repo = m[1];
                    if (repos.has(repo)) {
                        if (repo == "central") {
                            repo = "nightly";
                        }
                        const rev = m[2];
                        hgurls.push("h=" + repo + "|" + rev);
                    }
                }
            }
        });
        //const crashStop = "https://localhost:5000";
        const crashStop = "https://crash-stop.herokuapp.com";
        const sumup = crashStop + "/sumup.html";
        const crashStopLink = encodeURI(sumup + "?" + hgurls.join("&") + "&" + signatures.join("&"));
        const iframe = document.createElement("iframe");
        const div = document.createElement("div");
        iframe.setAttribute("src", crashStopLink);
        iframe.setAttribute("id", "crash-stop-iframe");
        iframe.setAttribute("style", "display:block;top:0px;left:0px;width:100%;height:100%;border:0px;");
        iframe.setAttribute("scrolling", "no");
        div.setAttribute("style", "display:block;height:100%;");
        div.appendChild(iframe);
        container.insertBefore(div, container.lastElementChild);
        window.addEventListener("message", function (e) {
            if (e.origin == crashStop) {
                const iframe = document.getElementById("crash-stop-iframe");
                iframe.style.height = e.data + "px";

            }
        });
    }
}
