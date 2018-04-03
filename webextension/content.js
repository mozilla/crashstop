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
            signatures.push("s=" + escape(s));
        }
    });
    if (signatures.length != 0) {
        const extraSocorroArgs = []
        const baseUrl = "https://crash-stats.mozilla.com/search/";
        const sayNo = new Set(["_columns", "_facets", "_facets_size", "_sort", "_results_number", "date", "channel", "product", "version", "build_id"]);
        const urlSelector = oldWay ? "bz_url_edit_container" : "field-value-bug_file_loc";
        document.querySelectorAll("#" + urlSelector + " a").forEach(a => {
            if (a.href.startsWith(baseUrl)) {
                const params = new URLSearchParams(a.href.slice(baseUrl.length));
                for (let p of params) {
                    if (!sayNo.has(p[0])) {
                        extraSocorroArgs.push(p[0] + "=" + escape(p[1]));
                    }
                }
            }
        });
        const hgurlPattern = new RegExp("^http[s]?://hg\\.mozilla\\.org/(?:releases/)?mozilla-([^/]*)/rev/([0-9a-f]+)$");
        const esrPattern = new RegExp("^esr[0-9]+$");
        const repos = new Set(["central", "beta", "release"]);
        const hgrevs = [];
        let isFirst = false;
        let currentCommentId = "";
        const aSelector = oldWay ? ".bz_comment_text > a" : ".comment-text > a";
        document.querySelectorAll(aSelector).forEach(a => {
            const parentId = a.parentNode.attributes.id;
            let hasBugherderKw = false;
            let hasUpliftKw = false;
            if (parentId !== currentCommentId) {
                // we're in a new comment
                currentCommentId = parentId;
                isFirst = false;
                // here we check that we've bugherder or uplift keyword
                let commentTagSelector = "";
                let x = "";
                if (oldWay) {
                    const parts = parentId.value.split("_");
                    if (parts.length == 3) {
                        const num = parts[2];
                        const ctag = "comment_tag_" + num;
                        commentTagSelector = "#" + ctag + " .bz_comment_tag";
                        x = "x" + String.fromCharCode(160); // &nbsp;
                    }
                } else {
                    const parts = parentId.value.split("-");
                    if (parts.length == 2) {
                        const num = parts[1];
                        const ctag = "ctag-" + num;
                        commentTagSelector = "#" + ctag + ">.comment-tags>.comment-tag";
                        x = "x";
                    }
                }
                if (commentTagSelector) {
                    const xb = x + "bugherder";
                    const xu = x + "uplift";
                    document.querySelectorAll(commentTagSelector).forEach(span => {
                        const text = span.innerText;
                        if (!hasBugherderKw) {
                            hasBugherderKw = text === xb;
                        }
                        if (!hasUpliftKw) {
                            hasUpliftKw = text === xu;
                        }
                    });
                }
            }
            const prev = a.previousSibling;
            if (prev == null || (prev.previousSibling == null && !prev.textContent.trim())) {
                // the first element in the comment is the link (no text before)
                isFirst = true;
            }
            if (isFirst || hasBugherderKw || hasUpliftKw) {
                // so we take the first link and the following ones only if they match the pattern
                const link = a.href;
                const m = link.match(hgurlPattern);
                if (m != null) {
                    let repo = m[1];
                    if (repos.has(repo) || repo.match(esrPattern)) {
                        if (repo === "central") {
                            repo = "nightly";
                        }
                        let rev = m[2];
                        if (rev.length > 12) {
                            rev = rev.slice(0, 12);
                        }
                        hgrevs.push("h=" + repo + "%7C" /* | */ + rev);
                    }
                }
            }
        });

        //const crashStop = "https://localhost:5000";
        const crashStop = "https://crash-stop.herokuapp.com";
        const sumup = crashStop + "/sumup.html";
        const hpart = hgrevs.length != 0 ? (hgrevs.join("&") + "&") : "";
        const spart = signatures.join("&") + "&";
        const extra = extraSocorroArgs.join("&");
        const crashStopLink = sumup + "?" + hpart + spart + extra;
        const LSName = "Crash-Stop-V1";
        const iframe = document.createElement("iframe");
        let bugid;
        if (oldWay) {
            bugid = document.getElementById("shorturl").getAttribute("href").slice("https://bugzil.la/".length);
        } else {
            bugid = document.getElementById("this-bug").innerText.split(" ")[1];
        }
        window.addEventListener("message", function (e) {
            if (e.origin == crashStop) {
                const iframe = document.getElementById("crash-stop-iframe");
                iframe.style.height = e.data + "px";
            }
        });
        iframe.setAttribute("src", crashStopLink);
        iframe.setAttribute("id", "crash-stop-iframe");
        iframe.setAttribute("tabindex", "0");
        iframe.setAttribute("style", "display:block;width:100%;height:100%;border:0px;");
        const titleDiv = document.createElement("div");
        titleDiv.setAttribute("title", "Hide crash-stop");
        titleDiv.setAttribute("style", "display:inline;cursor:pointer;color:black;font-size:13px");
        const spinner = document.createElement("span");
        spinner.setAttribute("role", "button");
        spinner.setAttribute("tabindex", "0");
        spinner.setAttribute("style", "padding-right:5px;cursor:pointer;color:#999;");

        function hide() {
            spinner.innerText = "▸";
            spinner.setAttribute("aria-expanded", "false");
            spinner.setAttribute("aria-label", "show crash-stop");
            titleDiv.innerText = "Show table";
        };
        function show() {
            spinner.innerText = "▾";
            spinner.setAttribute("aria-expanded", "true");
            spinner.setAttribute("aria-label", "hide crash-stop");
            titleDiv.innerText = "Hide table";
        };
        function getLSData(id) {
            const s = localStorage.getItem(LSName);
            if (typeof id === "undefined") {
                return s === null ? new Object() : JSON.parse(s);
            } else {
                return s === null ? false : JSON.parse(s).hasOwnProperty(id);
            }
        }
        function setLSData(id) {
            const o = getLSData();
            o[bugid] = 1;
            localStorage.setItem(LSName, JSON.stringify(o));
        }
        function unsetLSData(id) {
            const o = getLSData();
            if (o.hasOwnProperty(id)) {
                delete o[bugid];
                localStorage.setItem(LSName, JSON.stringify(o));
            }
        }
        function toggle() {
            if (spinner.getAttribute("aria-expanded") === "true") {
                iframe.style.display = 'none';
                hide();
                setLSData(bugid);
            } else {
                if (!rightDiv.contains(iframe)) {
                    rightDiv.append(iframe);
                }
                iframe.style.display = 'block';
                show();
                unsetLSData(bugid);
            }
        };
        function toggleOnKey(e) {
            if (e.keyCode == 13 || e.keyCode == 32) {
                toggle();
            }
        };

        spinner.addEventListener("click", toggle, false);
        spinner.addEventListener("keydown", toggleOnKey, false);
        titleDiv.addEventListener("click", toggle, false);
        titleDiv.addEventListener("keydown", toggleOnKey, false);
        const spanSpinner = document.createElement("span");
        spanSpinner.append(spinner, titleDiv);
        const rightDiv = document.createElement("div");
        rightDiv.setAttribute("class", "value");
        rightDiv.append(spanSpinner);
        //localStorage.removeItem(LSName);
        if (getLSData(bugid)) {
            hide();
        } else {
            rightDiv.append(iframe);
            show();
        }
        if (oldWay) {
            const tr = document.createElement("tr");
            const th = document.createElement("th");
            th.setAttribute("class", "field_label");
            tr.append(th);
            const a = document.createElement("a");
            a.setAttribute("class", "field_help_link");
            a.setAttribute("title", "Crash data from Bugzilla Crash Stop addon");
            a.setAttribute("href", "https://addons.mozilla.org/firefox/addon/bugzilla-crash-stop/");
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
