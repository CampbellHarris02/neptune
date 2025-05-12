// ── Render chart from /chart_data ───────────────────────────────────────────
async function drawChart() {
    try {
      const res = await fetch('/chart_data');
      if (!res.ok) return;
  
      const { labels, values } = await res.json();
      const chart = echarts.init(document.getElementById('pnlCanvas'), 'dark');
  
      chart.setOption({
        title: { text: 'Account % PnL Over Time', textStyle: { color: '#fff' } },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: labels },
        yAxis: {
          type: 'value',
          axisLabel: { formatter: '{value} %' },
          splitLine: { lineStyle: { color: '#333' } }
        },
        series: [{
          name: 'PnL',
          type: 'line',
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2 },
          itemStyle: { color: '#45b3ff' },
          data: values
        }]
      });
    } catch (e) {
      console.warn("chart fetch failed:", e);
    }
  }
  
  // ── Update asset box from /assets_usd ───────────────────────────────────────
  async function refreshAssets() {
    try {
      const r = await fetch('/assets_usd');
      if (!r.ok) return;
  
      const j = await r.json();  // { value_usd: 123.75, pct_pnl: 0.0 }
  
      document.getElementById('assetValue').textContent =
        '$ ' + j.value_usd.toLocaleString(undefined, { minimumFractionDigits: 2 });
  
      const sign = j.pct_pnl >= 0 ? '+' : '–';
      document.getElementById('assetDelta').textContent =
        `Δ ${sign}${Math.abs(j.pct_pnl).toFixed(2)} %`;
  
      document.getElementById('assetDelta').style.color =
        j.pct_pnl >= 0 ? '#37d67a' : '#f44336';
    } catch (e) {
      console.warn("asset refresh failed:", e);
    }
  }
  
  // ── Load on page ready ──────────────────────────────────────────────────────
  window.addEventListener("DOMContentLoaded", () => {
    drawChart();
    refreshAssets();
    setInterval(refreshAssets, 15000);
  });
  