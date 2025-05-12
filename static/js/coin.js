const chart = echarts.init(document.getElementById("chart"), "dark");
const tfBtns = document.querySelectorAll(".tf-btn");
const listDiv = document.getElementById("eventsList");

tfBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    tfBtns.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    loadAndDraw(btn.dataset.tf);
  });
});

window.addEventListener("DOMContentLoaded", () => {
  loadAndDraw("1d");
});

/* Load data and draw chart -------------------------------------------------- */
function loadAndDraw(tf) {
  fetch(`/coin_data?symbol=${encodeURIComponent(symbol)}&tf=${tf}`)
    .then((r) => (r.ok ? r.json() : Promise.reject(tf)))
    .then(draw)
    .catch((bad) => {
      chart.clear();
      chart.setOption({
        title: {
          text: `No data for ${bad}`,
          left: "center",
          top: "40%",
          textStyle: { color: "#ccc" },
        },
      });
      listDiv.innerHTML = "";
    });
}

/* Draw chart and add buy/sell arrows ---------------------------------------- */
function draw(p) {
  if (!p.series?.length) {
    chart.clear();
    chart.setOption({
      title: {
        text: "No candles",
        left: "center",
        top: "40%",
        textStyle: { color: "#ccc" },
      },
    });
    listDiv.innerHTML = "";
    return;
  }

  const xs = p.series.map((c) => c.t);
  const ohlc = p.series.map((c) => [c.o, c.c, c.l, c.h]);

  const buyPts = [];
  const sellPts = [];

  p.events.forEach((e) => {
    const item = {
      value: [e.time, e.price],
      symbol: "triangle",
      symbolSize: 9,
    };
    if (e.side === "buy") {
      buyPts.push({ ...item, itemStyle: { color: "#3fdb6f" } });
    } else {
      sellPts.push({
        ...item,
        itemStyle: { color: "#f44336" },
        symbolRotate: 180,
      });
    }
  });

  chart.setOption({
    animation: false,
    dataZoom: [
      { type: "inside", xAxisIndex: 0, throttle: 50 },
      {
        type: "slider",
        xAxisIndex: 0,
        height: 18,
        handleSize: "80%",
        bottom: 8,
        fillerColor: "#444",
      },
      {
        type: "inside",
        yAxisIndex: 0,
        orient: "vertical",
        filterMode: "none",
      },
    ],
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    xAxis: {
      type: "category",
      data: xs,
      scale: true,
      axisLine: { onZero: false },
    },
    yAxis: { scale: true },
    grid: { left: "8%", right: "6%", top: 60, bottom: 60 },
    series: [
      {
        type: "candlestick",
        name: "OHLC",
        data: ohlc,
        itemStyle: {
          color: "#45b3ff",
          color0: "#d35454",
          borderColor: "#45b3ff",
          borderColor0: "#d35454",
        },
      },
      { name: "Buy", type: "scatter", data: buyPts },
      { name: "Sell", type: "scatter", data: sellPts },
    ],
  });

  listDiv.innerHTML = p.events
    .slice()
    .sort((a, b) => b.time.localeCompare(a.time))
    .map(
      (ev) => `
    <div class="event-row event-${ev.side}">
      <span>${ev.time.replace("T", " ").replace("Z", "")}</span>
      <span>${ev.side.toUpperCase()} @ ${ev.price}</span>
      <span>${ev.qty}</span>
    </div>`
    )
    .join("");
}
