// live_pnl main.go  – paste over the previous file
package main

import (
	"bytes"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"html/template"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/go-echarts/go-echarts/v2/charts"
	"github.com/go-echarts/go-echarts/v2/opts"
)

/* ─── locations & parameters ─────────────────────────────────────────────── */

const (
	staticDir   = "./static"
	templateDir = "./templates"
	chartDir    = "./static/charts"
	pnlCSV      = "./data/mock_pnl.csv"
	tradesJSON  = "./data/mock_trades.json"
	accountCSV  = "./data/account_pnl.csv"
	mockSymbol  = "BTC/USD"

	daysBack      = 90
	chartWidthIn  = 6
	chartHeightIn = 4
)

/* ─── models ─────────────────────────────────────────────────────────────── */

type Trade struct {
	Symbol string  `json:"symbol"`
	Side   string  `json:"side"`
	Qty    float64 `json:"amount"`
	Price  float64 `json:"price"`
	Time   string  `json:"time"`
}

/* ─── global SSE hub ─────────────────────────────────────────────────────── */

var (
	clients   = make(map[chan struct{}]struct{})
	clientsMu sync.Mutex
)

func broadcast() {
	clientsMu.Lock()
	for ch := range clients {
		select {
		case ch <- struct{}{}: //  ← colon after case
		default: //  ← colon after default
		}
	}
	clientsMu.Unlock()
}

func addClient() chan struct{} {
	ch := make(chan struct{}, 1)
	clientsMu.Lock()
	clients[ch] = struct{}{}
	clientsMu.Unlock()
	return ch
}

func removeClient(ch chan struct{}) {
	clientsMu.Lock()
	delete(clients, ch)
	clientsMu.Unlock()
}

/* ─── main ───────────────────────────────────────────────────────────────── */

func main() {
	must(os.MkdirAll(chartDir, 0o755))
	must(os.MkdirAll("data", 0o755))

	r := gin.Default()

	r.SetFuncMap(template.FuncMap{
		"now": func() int64 { return time.Now().Unix() },
		"add": func(a, b int) int { return a + b }, // 1-based index helper
	})

	r.LoadHTMLGlob(filepath.Join(templateDir, "*.html"))

	r.Static("/static", staticDir)

	r.GET("/", func(c *gin.Context) { c.HTML(http.StatusOK, "home.html", nil) })
	r.StaticFile("/assets_usd", "./data/assets_usd.json")

	r.GET("/chart", func(c *gin.Context) {
		c.Header("HX-Trigger", "chart-refreshed")
		c.Header("Content-Type", "text/html")
		html := `<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.2/dist/echarts.min.js"></script>`
		html += buildLineChartHTML()
		c.String(http.StatusOK, html)
	})

	r.GET("/strategy", func(c *gin.Context) {
		coins, err := loadRankedCoins()
		if err != nil {
			c.String(http.StatusInternalServerError, "cannot load file: %v", err)
			return
		}
		c.HTML(http.StatusOK, "strategy.html", gin.H{
			"Coins":  coins,
			"Header": makeHeader("/", "← Home"),
		})
	})

	r.GET("/portfolio", func(c *gin.Context) {
		pos, err := loadPortfolio()
		if err != nil {
			c.String(http.StatusInternalServerError, "cannot load file: %v", err)
			return
		}
		c.HTML(http.StatusOK, "portfolio.html", gin.H{
			"Positions": pos,
			"Header":    makeHeader("/", "← Home"),
		})
	})

	// HTML page
	r.GET("/coin", func(c *gin.Context) {
		sym := c.Query("symbol")
		from := c.DefaultQuery("from", "portfolio") // fallback
		backURL, backLabel := "/portfolio", "← Portfolio"
		if from == "strategy" {
			backURL, backLabel = "/strategy", "← Strategy"
		}
		c.HTML(http.StatusOK, "coin.html", gin.H{
			"Symbol": sym,
			"Header": makeHeader(backURL, backLabel),
		})
	})

	r.GET("/coin_data", func(c *gin.Context) {
		sym := c.Query("symbol")
		tf := c.DefaultQuery("tf", "1d")

		payload, err := loadCoinPayload(sym, tf)
		if err != nil {
			// log server-side and send 404 so JS can react
			log.Printf("coin_data error: %v", err)
			c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
			return
		}
		// empty series → still 200 so chart draws nothing but doesn't crash
		c.JSON(http.StatusOK, payload)
	})

	log.Println("📡  http://localhost:8080")
	must(r.Run(":8080"))
}

// models.go or near the other helpers
type Position struct {
	Symbol   string  `json:"symbol"`
	Quantity float64 `json:"quantity"`
}

// returns the slice sorted alphabetically (or change to suit)
func loadPortfolio() ([]Position, error) {
	f, err := os.Open("data/portfolio.json")
	if err != nil {
		return nil, err
	}
	defer f.Close()

	var raw map[string]float64
	if err = json.NewDecoder(f).Decode(&raw); err != nil {
		return nil, err
	}

	var out []Position
	for sym, qty := range raw {
		out = append(out, Position{sym, qty})
	}

	sort.Slice(out, func(i, j int) bool { return out[i].Symbol < out[j].Symbol })
	return out, nil
}

func fp(v float64) string { return strconv.FormatFloat(v, 'f', 2, 64) }

func must(err error) {
	if err != nil {
		log.Fatal(err)
	}
}
func fileExists(p string) bool { _, e := os.Stat(p); return e == nil }

/*──────────────── buildLineChartHTML ───────────────*/
func buildLineChartHTML() string {
	pts := loadAccountPNL(true) // true → use USD value column
	// pts := loadAccountPNL(false) // uncomment if you prefer %-PnL

	xs := make([]string, len(pts))
	ys := make([]opts.LineData, len(pts))
	for i, p := range pts {
		xs[i] = p.T
		ys[i] = opts.LineData{Value: p.V}
	}

	line := charts.NewLine()
	line.SetGlobalOptions(
		charts.WithInitializationOpts(opts.Initialization{
			Width: "100%", Height: "500px", Theme: "dark",
		}),
		charts.WithTitleOpts(opts.Title{Title: "Account Value (USD)",
			Left: "center", Top: "20"}),
		charts.WithXAxisOpts(opts.XAxis{Type: "category"}),
		charts.WithYAxisOpts(opts.YAxis{
			Name: "USD", NameLocation: "end", NameGap: 20,
			SplitLine: &opts.SplitLine{Show: opts.Bool(true)},
		}),
		charts.WithGridOpts(opts.Grid{Left: "6%", Right: "5%",
			Top: "15%", Bottom: "15%", ContainLabel: opts.Bool(true)}),
	)
	line.SetXAxis(xs).
		AddSeries("Value", ys).
		SetSeriesOptions(
			charts.WithLineChartOpts(opts.LineChart{
				Smooth: opts.Bool(true), ShowSymbol: opts.Bool(false)}),
			charts.WithAreaStyleOpts(opts.AreaStyle{Opacity: 0.15, Color: "#5ab0ff"}),
		)

	var buf bytes.Buffer
	_ = line.Render(&buf)
	return fmt.Sprintf(`<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.2/dist/echarts.min.js"></script>%s`,
		buf.String())
}

type point struct {
	T string
	Y float64
}

type RankedCoin struct {
	Symbol string  `json:"-"`
	Score  float64 `json:"score"`
	Price  float64 `json:"price"`
}

func loadRankedCoins() ([]RankedCoin, error) {
	f, err := os.Open("data/ranked_coins.json")
	if err != nil {
		return nil, err
	}
	defer f.Close()

	// the JSON is an object of objects → decode into generic map first
	var raw map[string]RankedCoin
	if err = json.NewDecoder(f).Decode(&raw); err != nil {
		return nil, err
	}

	coins := make([]RankedCoin, 0, len(raw))
	for sym, rc := range raw {
		rc.Symbol = sym
		coins = append(coins, rc)
	}

	sort.Slice(coins, func(i, j int) bool { return coins[i].Score > coins[j].Score })
	return coins, nil
}

// ---------------------------------------------------------------------
// load 1-day CSV and events.json for a symbol
// ---------------------------------------------------------------------

// -----------------------------------------------------------------------------
// Coin types
// -----------------------------------------------------------------------------
type CoinPoint struct {
	T string  `json:"t"` // keep as string (category axis)
	O float64 `json:"o"`
	H float64 `json:"h"`
	L float64 `json:"l"`
	C float64 `json:"c"`
}

type CoinEvent struct {
	Time  string  `json:"time"`
	Side  string  `json:"side"` // "buy"/"sell"
	Price float64 `json:"price"`
	Qty   float64 `json:"qty"`
}

type CoinPayload struct {
	Symbol string      `json:"symbol"`
	Series []CoinPoint `json:"series"`
	Events []CoinEvent `json:"events"`
}

// -----------------------------------------------------------------------------
// Helper
// -----------------------------------------------------------------------------
func loadCoinPayload(sym, tf string) (CoinPayload, error) {
	folder := symbolDir(sym) // e.g. btc_usd
	base := filepath.Join("data", "historical", folder)

	// ---- candles CSV ----------------------------------------------------------
	csvPath := filepath.Join(base, tf+".csv")
	f, err := os.Open(csvPath)
	if err != nil {
		return CoinPayload{}, fmt.Errorf("open csv: %w", err)
	}
	defer f.Close()

	r := csv.NewReader(f)
	records, err := r.ReadAll()
	if err != nil {
		return CoinPayload{}, fmt.Errorf("csv read: %w", err)
	}

	var series []CoinPoint
	for i, rec := range records {
		// optional: skip header row — detect by trying to parse price
		if i == 0 {
			if _, err := strconv.ParseFloat(rec[1], 64); err != nil {
				continue // header
			}
		}
		if len(rec) < 5 {
			continue // need o,h,l,c
		}

		o, _ := strconv.ParseFloat(rec[1], 64)
		h, _ := strconv.ParseFloat(rec[2], 64)
		l, _ := strconv.ParseFloat(rec[3], 64)
		c_, _ := strconv.ParseFloat(rec[4], 64)

		series = append(series, CoinPoint{rec[0], o, h, l, c_})

	}

	// ---- events ---------------------------------------------------------------
	evtPath := filepath.Join(base, "events.json")
	ef, err := os.Open(evtPath)
	if err != nil {
		return CoinPayload{}, fmt.Errorf("open events: %w", err)
	}
	defer ef.Close()

	var events []CoinEvent
	if err := json.NewDecoder(ef).Decode(&events); err != nil {
		return CoinPayload{}, fmt.Errorf("decode events: %w", err)
	}

	return CoinPayload{Symbol: sym, Series: series, Events: events}, nil
}

// btc_usd folder path for "BTC/USD"
func symbolDir(sym string) string {
	return strings.ReplaceAll(strings.ToLower(sym), "/", "_")
}

func readStatus() string {
	b, err := os.ReadFile("status.txt")
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}

type HeaderData struct {
	Back      string
	BackLabel string
	Status    string
}

func makeHeader(backURL, label string) HeaderData {
	return HeaderData{Back: backURL, BackLabel: label, Status: readStatus()}
}

type Candle struct {
	T          string  `json:"t"`
	O, H, L, C float64 `json:"o","h","l","c"`
}

type pnlPoint struct {
	T string  // date (YYYY-MM-DD)
	V float64 // value or pct
}

func loadAccountPNL(valueNotPct bool) []pnlPoint {
	f, err := os.Open(accountCSV)
	if err != nil {
		return nil
	}
	defer f.Close()

	r := csv.NewReader(f)
	_, _ = r.Read() // discard header

	var out []pnlPoint
	for {
		rec, err := r.Read()
		if err != nil {
			break
		}
		vField := 1
		if !valueNotPct {
			vField = 2
		} // column 2 == pct_pnl
		v, _ := strconv.ParseFloat(rec[vField], 64)
		out = append(out, pnlPoint{rec[0], v})
	}
	return out
}
