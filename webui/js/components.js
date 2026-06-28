/* components.js — tiny DOM builders mirroring src/pippal/ui/theme.py's
 * make_card() + the row helpers in settings_cards.py. No framework;
 * the surface is simple enough that plain DOM keeps the CSS
 * a 1:1 match of the Tk styles. */
(function () {
  "use strict";

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "class") node.className = attrs[k];
        else if (k === "text") node.textContent = attrs[k];
        else if (k === "html") node.innerHTML = attrs[k];
        else if (k.indexOf("data-") === 0 || k === "type" || k === "value" ||
                 k === "min" || k === "max" || k === "step" ||
                 k === "placeholder" || k === "title" || k === "for" ||
                 k === "aria-label" || k === "role")
          node.setAttribute(k, attrs[k]);
        else if (k === "testid") node.setAttribute("data-testid", attrs[k]);
        else node[k] = attrs[k];
      });
    }
    (children || []).forEach(function (c) {
      if (c == null) return;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  /** Card with an optional uppercase section title (theme.make_card). */
  function card(title, children) {
    var kids = [];
    if (title) kids.push(el("div", { class: "card-title", text: title }));
    (children || []).forEach(function (c) { kids.push(c); });
    return el("div", { class: "card" }, kids);
  }

  function hint(text) {
    return el("div", { class: "card-hint", text: text });
  }

  /** Labelled field row (label width matches the Tk width=14 column). */
  function fieldRow(labelText, control) {
    return el("div", { class: "row" }, [
      el("label", { class: "field-label", text: labelText }),
      control,
    ]);
  }

  function select(testid, options, value) {
    var s = el("select", { testid: testid });
    options.forEach(function (opt) {
      var o = el("option", { value: opt.value, text: opt.label });
      if (opt.value === value) o.selected = true;
      s.appendChild(o);
    });
    return s;
  }

  function checkRow(testid, labelText, checked) {
    var box = el("input", { type: "checkbox", testid: testid });
    box.checked = !!checked;
    return el("label", { class: "checkrow" }, [box, el("span", { text: labelText })]);
  }

  function sliderRow(labelText, testid, min, max, step, value, fmt) {
    var slider = el("input", {
      type: "range", testid: testid,
      min: String(min), max: String(max), step: String(step),
    });
    slider.value = String(value);
    var out = el("span", { class: "slider-value", testid: testid + "-value",
                            text: fmt(value) });
    slider.addEventListener("input", function () {
      out.textContent = fmt(parseFloat(slider.value));
    });
    return {
      node: el("div", { class: "row" }, [
        el("label", { class: "field-label", text: labelText }),
        slider, out,
      ]),
      slider: slider,
      valueEl: out,
    };
  }

  function spinRow(labelText, testid, min, max, step, value, unit) {
    var input = el("input", {
      type: "number", testid: testid,
      min: String(min), max: String(max), step: String(step),
    });
    input.value = String(value);
    input.style.width = "84px";
    return {
      node: el("div", { class: "row" }, [
        el("label", { class: "field-label", text: labelText }),
        input,
        el("span", { class: "card-hint", text: unit }),
      ]),
      input: input,
    };
  }

  window.UI = {
    el: el, card: card, hint: hint, fieldRow: fieldRow,
    select: select, checkRow: checkRow, sliderRow: sliderRow, spinRow: spinRow,
  };
})();
