(function() {
    document.body.classList.add('hide-controls');

    document.getElementById('langs').addEventListener('change', function() {
      if (this.value !== "") {
        location.href = "/" + this.value + "/" + polyglot.path;
      }
    });

    var lines = document.querySelectorAll('.line > span');
    var node;

    for (var i = 0; i < lines.length; ++i) {
      lines[i].style.display = "none";
      node = document.createElement("span");
      node.setAttribute('class', 'md');
      node.innerHTML = markdown.toHTML(lines[i].innerHTML.trim());
      lines[i].parentNode.insertBefore(node, lines[i]);
    }

    var edits = document.querySelectorAll(".btn-edit");
    for (var i = 0; i < edits.length; ++i) {
        edits[i].addEventListener('click', function() {
            var parentLine = this.parentNode.parentNode;
            var parentControls = this.parentNode;
            var lineData = parentLine.querySelector('.line-data');

            if (this.style.display === "none") {
              lineData.style.display = "";
              parentLine.removeChild(
                  parentLine.querySelector('.form-edit'));
              return;
            }
            var form = document.createElement("form");
            form.method = "post";
            form.setAttribute('class', 'form-edit');

            var lineNo = document.createElement("input");
            lineNo.type = "hidden";
            lineNo.name = "line";
            lineNo.value = Array.prototype.indexOf.call(
                parentLine.parentNode.children, parentLine);
            form.appendChild(lineNo);

            var content = document.createElement("textarea");
            content.name = "data";
            content.value = lineData.innerHTML.trim();
            content.style.width = "100%";
            content.style.boxSizing = "border-box";
            form.appendChild(content);

            form.appendChild(document.createElement("br"));

            var submit = document.createElement("input");
            submit.type = "submit";
            form.appendChild(submit);

            var cancel = document.createElement("button");
            cancel.type = "button";
            cancel.innerHTML = "Cancel";
            form.appendChild(cancel);

            cancel.addEventListener("click", function() {
                var parent = parentLine;
                parent.querySelector('.controls').display = "";
                parent.querySelector('.md').style.display = "";
                parent.removeChild(parentControls);
            });

            parentLine.querySelector('.md').style.display = "none";
            parentControls.style.display = "none";
            parentLine.appendChild(form);
        });
    }

    var newlines = document.querySelectorAll(".btn-newline");
    for (var i = 0; i < newlines.length; ++i) {
        newlines[i].addEventListener('click', function() {
            var parentLine = this.parentNode.parentNode;
            var parentControls = this.parentNode;

            var form = document.createElement("form");
            form.method = "post";

            var newline = document.createElement("input");
            newline.type = "hidden";
            newline.name = "insert";
            newline.value = "true";
            form.appendChild(newline);

            var lineNo = document.createElement("input");
            lineNo.type = "hidden";
            lineNo.name = "line";
            lineNo.value = Array.prototype.indexOf.call(parentLine.parentNode.children, parentLine);
            form.appendChild(lineNo);

            var content = document.createElement("textarea");
            content.name = "data";
            content.style.width = "100%";
            content.style.boxSizing = "border-box";
            form.appendChild(content);

            form.appendChild(document.createElement("br"));

            var submit = document.createElement("input");
            submit.type = "submit";
            form.appendChild(submit);

            var cancel = document.createElement("button");
            cancel.type = "button";
            cancel.innerHTML = "Cancel";
            form.appendChild(cancel);

            cancel.addEventListener("click", function() {
                parentLine.removeChild(this.parentNode);
            });

            parentLine.insertBefore(form, parentLine.children[0]);
        });
    }

    document.querySelector(".btn-togglecontrols")
    .addEventListener('click', function() {
        document.body.classList.toggle("hide-controls");
    });
})()
