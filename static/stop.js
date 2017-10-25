function getParams() {
    let params = ["channel", "product"].map(function(i) {
        let e = document.getElementById(i);
        return e.options[e.selectedIndex].value;
    });
    return params;
}

function update() {
    let params = getParams();
    location.href = "signatures.html?channel=" + params[0]
                  + "&product=" + params[1];
}

function bug() {
    let bugid = document.getElementById("bugid").value;
    location.href = "bug.html?id=" + bugid;
}

