/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

"use strict";

let oldWay = false;
let container = document.getElementById("module-details-content");
if (!container) {
    container = document.getElementById("field_label_cf_crash_signature");
    oldWay = true;
}
if (container) {
    const signatures = [];
    const selector = oldWay ? "cf_crash_signature_edit_container" : "field-value-cf_crash_signature";
    document.querySelectorAll("#" + selector + " a").forEach(a => {
        if (a.href.startsWith("https://crash-stats.mozilla.com/signature")) {
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
        }
    });
    if (signatures.length != 0) {
        const hgurlPattern = new RegExp("^http[s]?://hg\\.mozilla\\.org/(?:releases/)?mozilla-([^/]*)/rev/([0-9a-f]+)$");
        const repos = new Set(["central", "beta", "release"]);
        const hgrevs = [];
        let isFirst = false;
        let currentCommentId = "";
        const aSelector = oldWay ? ".bz_comment_text > a" : ".comment-text > a";
        document.querySelectorAll(aSelector).forEach(a => {
            const parentId = a.parentNode.attributes.id;
            if (parentId !== currentCommentId) {
                // we're in a new comment
                currentCommentId = parentId;
                isFirst = false;
            }
            const prev = a.previousSibling;
            if (prev == null || (prev.previousSibling == null && !prev.textContent.trim())) {
                // the first element in the comment is the link (no text before)
                isFirst = true;
            }
            if (isFirst) {
                // so we take the first link and the following ones only if they match the pattern
                const link = a.href;
                const m = link.match(hgurlPattern);
                if (m != null) {
                    let repo = m[1];
                    if (repos.has(repo)) {
                        if (repo === "central") {
                            repo = "nightly";
                        }
                        let rev = m[2];
                        if (rev.length > 12) {
                            rev = rev.slice(0, 12);
                        }
                        hgrevs.push("h=" + repo + "|" + rev);
                    }
                }
            }
        });
        //const crashStop = "https://localhost:5000";
        const crashStop = "https://crash-stop.herokuapp.com";
        const sumup = crashStop + "/sumup.html";
        const hpart = hgrevs.length != 0 ? (hgrevs.join("&") + "&") : "";
        const spart = signatures.join("&");
        const crashStopLink = encodeURI(sumup + "?" + hpart + spart);
        const iframe = document.createElement("iframe");
        window.addEventListener("message", function (e) {
            if (e.origin == crashStop) {
                const iframe = document.getElementById("crash-stop-iframe");
                iframe.style.height = e.data + "px";
            }
        });
        iframe.setAttribute("src", crashStopLink);
        iframe.setAttribute("id", "crash-stop-iframe");
        iframe.setAttribute("style", "display:block;width:100%;height:100%;border:0px;");
        iframe.setAttribute("scrolling", "no");
        const rightDiv = document.createElement("div");
        rightDiv.setAttribute("class", "value");
        rightDiv.append(iframe);
        if (oldWay) {
            const tr = document.createElement("tr");
            const th = document.createElement("th");
            th.setAttribute("class", "field_label");
            tr.append(th);
            const a = document.createElement("a");
            a.setAttribute("class", "field_help_link");
            a.setAttribute("title", "Crash data from Bugzilla Crash Stop addon");
            a.setAttribute("href", "https://addons.mozilla.org/en-US/firefox/addon/bugzilla-crash-stop/");
            a.innerText = "Crash data:";
            th.append(a);
            const td = document.createElement("td");
            td.setAttribute("class", "field_value");
            td.setAttribute("colspan", 2);
            td.append(rightDiv);
            tr.append(td);
            container = container.parentNode;
            container.parentNode.insertBefore(tr, container.nextSibling);
        } else {
            const mainDiv = document.createElement("div");
            mainDiv.setAttribute("class", "field");
            const leftDiv = document.createElement("div");
            leftDiv.setAttribute("class", "name");
            leftDiv.innerText = "Crash Data:";
            mainDiv.append(leftDiv, rightDiv);
            container.append(mainDiv);
        }
    }
}
