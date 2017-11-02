/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

let selector = document.getElementById("cf_crash_signature_edit_container") ? "cf_crash_signature_edit_container" : "field-value-cf_crash_signature";
let container = document.getElementById(selector);
if (container) {
    let signatures = ""
    document.querySelectorAll("#" + selector + " a").forEach(a => signatures += a.innerText.trim());
    if (signatures) {
        let hgurlPattern = new RegExp("^http[s]?://hg\.mozilla\.org/(?:releases/)?mozilla-([^/]*)/rev/[0-9a-f]+$");
        let repos = new Set(["central", "beta", "release"]);
        let hgurls = [];
        let isFirst = false;
        document.querySelectorAll(".comment-text > a").forEach(a => {
            let prev = a.previousSibling;
            if (prev == null || (prev.previousSibling == null && !prev.textContent.trim())) {
                isFirst = true;
            }
            if (isFirst) {
                let link = a.href;
                let m = link.match(hgurlPattern);
                if (m != null && repos.has(m[1])) {
                    hgurls.push("hgurls=" + link);
                }
            }
        });
        let crashStop = "https://crash-stop.herokuapp.com/crashdata.html";
        let crashStopLink = crashStop + "?" + hgurls.join("&") + "&signatures=" + signatures;
        let div = document.createElement("div");
        let span = document.createElement("span");
        span.innerHTML = "See if the patches had a positive effect on crash numbers: ";
        let a = document.createElement("a");
        a.innerHTML = "crash-stop";
        a.setAttribute("href", crashStopLink);
        a.setAttribute("target", "_blank");
        span.appendChild(a);
        div.appendChild(span);
        container.insertBefore(div, container.lastElementChild);
    }
}
