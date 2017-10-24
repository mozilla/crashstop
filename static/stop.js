let isLoaded = false;

function loaded() {
    isLoaded = true;
}

function getParams() {
    let params = ["channel", "product"].map(function(i) {
        let e = document.getElementById(i);
        return e.options[e.selectedIndex].value;
    });
    return params;
}

function setHref(channel, product) {
    location.href = "signatures.html?channel=" + channel
                  + "&product=" + product;
}

function update() {
    let params = getParams();
    setHref(params[0], params[1]);
}

function bug() {
    let bugid = document.getElementById("bugid").value;
    location.href = "bug.html?id=" + bugid;
}

