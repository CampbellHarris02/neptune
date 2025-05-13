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






function draw(p) {
  // 1) No-data guard
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

  // 2) Prep data
  const stopLoss = p.stop_loss ?? null;
  const events   = Array.isArray(p.events) ? p.events : [];

  const momentumEl = document.getElementById("momentumLabel");
  const stopLossEl = document.getElementById("stopLossLabel");
  
  momentumEl.textContent =
    (p.momentum_score !== 0 ? p.momentum_score.toFixed(2) : "—");
  
  stopLossEl.textContent =
    (p.stop_loss !== 0 ? p.stop_loss.toFixed(4) : "—");
  
  // Optional: color momentum green/red
  if (p.momentum_score > 0.05) {
    momentumEl.style.color = "#3fdb6f";
  } else if (p.momentum_score < -0.05) {
    momentumEl.style.color = "#f44336";
  } else {
    momentumEl.style.color = "#e0e1dd";
  }
  


  // Build ohlc entries with timestamps
  const ohlc = p.series.map(c => [
    c.t,       // time ISO string
    c.o,       // open
    c.c,       // close
    c.l,       // low
    c.h        // high
  ]);

  // scatter markers
  const buyPts  = [];
  const sellPts = [];
  events.forEach(e => {
    const pt = { value: [e.time, e.price], symbol: "triangle", symbolSize: 9 };
    if (e.side === "buy")  buyPts.push({ ...pt, itemStyle: { color: "#3fdb6f" } });
    else                    sellPts.push({ ...pt, itemStyle: { color: "#f44336" }, symbolRotate: 180 });
  });

  // last‐buy/sell events
  const lastBuy  = [...events].reverse().find(e => e.side === "buy");
  const lastSell = [...events].reverse().find(e => e.side === "sell");

  // horizontal lines
  const hLines = [];
  if (stopLoss !== null) {
    hLines.push({
      yAxis: stopLoss,
      name: "SL",
      label: { show: true, position: "end", formatter: "SL", color: "#ffffff" },
      lineStyle: { type: "dashed", color: "#ffffff", width: 1.5 }
    });
  }
  if (lastBuy) {
    hLines.push({
      yAxis: lastBuy.price,
      name: "LB",
      label: { show: true, position: "end", formatter: "LB", color: "#3fdb6f" },
      lineStyle: { type: "dashed", color: "#3fdb6f", width: 1.5 }
    });
  }
  if (lastSell) {
    hLines.push({
      yAxis: lastSell.price,
      name: "LS",
      label: { show: true, position: "end", formatter: "LS", color: "#f44336" },
      lineStyle: { type: "dashed", color: "#f44336", width: 1.5 }
    });
  }

  // vertical lines
  const vLines = [];
  if (lastBuy) {
    vLines.push({
      xAxis: lastBuy.time,
      lineStyle: { type: "dashed", color: "#3fdb6f", width: 1 },
      label: { show: false }
    });
  }
  if (lastSell) {
    vLines.push({
      xAxis: lastSell.time,
      lineStyle: { type: "dashed", color: "#f44336", width: 1 },
      label: { show: false }
    });
  }

  // 3) Render chart
  chart.setOption({
    animation: false,
    dataZoom: [
      { type: "inside", xAxisIndex: 0, throttle: 50 },
      { type: "slider",  xAxisIndex: 0, height: 18, handleSize: "80%", bottom: 8, fillerColor: "#444" },
      { type: "inside",  yAxisIndex: 0, orient: "vertical", filterMode: "none" },
    ],
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    xAxis: {
      type: "time",
      scale: true,
      axisLine: { onZero: false }
    },
    yAxis: { scale: true },
    grid: { left: "8%", right: "6%", top: 60, bottom: 60 },
    series: [
      {
        type: "candlestick",
        name: "OHLC",
        data: ohlc,
        itemStyle: {
          color: "#45b3ff",   // up color
          color0: "#d35454",  // down color
          borderColor: "#45b3ff",
          borderColor0: "#d35454"
        },
        markLine: {
          silent: true,
          symbol: "none",
          data: [
            ...hLines,
            ...vLines
          ]
        }
      },
      { name: "Buy",  type: "scatter", data: buyPts },
      { name: "Sell", type: "scatter", data: sellPts }
    ]
  });

  // 4) Trade ledger
  listDiv.innerHTML = events
    .slice().sort((a,b)=>b.time.localeCompare(a.time))
    .map(ev => {
      const qty   = Number(ev.qty).toPrecision(6);
      const price = Number(ev.price).toFixed(2);
      const time  = ev.time.replace("T"," ").replace("Z","");
      return `
        <div class="event-row event-${ev.side}">
          <span>${time}</span>
          <span>${ev.side.toUpperCase()} @ ${price}</span>
          <span>${qty}</span>
        </div>`;
    })
    .join("");
}
