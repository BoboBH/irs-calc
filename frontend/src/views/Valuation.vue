<template>
  <div class="page">
    <header class="topbar">
      <span class="brand-sq"></span>
      <span class="brand">利率互换计算器</span>
      <span class="brand-sub">IRS Pricing · DV01 · Campisi 归因</span>
    </header>

    <div class="layout">
      <!-- 左:输入区 -->
      <aside class="input-panel">
        <div class="swap-bar"><span>Swap 合约</span></div>

        <section class="group">
          <div class="group-title">基础信息</div>
          <div class="grid2">
            <div class="field">
              <label>挂钩基准</label>
              <el-select v-model="form.benchmark">
                <el-option value="FR007" label="FR007" />
                <el-option value="SHIBOR3M" label="SHIBOR 3M" />
              </el-select>
            </div>
            <div class="field">
              <label>头寸方向</label>
              <el-radio-group v-model="form.direction" class="seg">
                <el-radio-button value="payer">付固定</el-radio-button>
                <el-radio-button value="receiver">收固定</el-radio-button>
              </el-radio-group>
            </div>
          </div>
          <div class="field" style="margin-top: 12px">
            <label>名义本金(元)</label>
            <el-input-number v-model="form.notional" :min="1" :step="10000000" :controls="false" />
          </div>
          <div class="grid2" style="margin-top: 12px">
            <div class="field">
              <label>起息日</label>
              <el-date-picker v-model="form.effectiveDate" type="date" value-format="YYYY-MM-DD" />
            </div>
            <div class="field">
              <label>到期日</label>
              <el-date-picker v-model="form.maturityDate" type="date" value-format="YYYY-MM-DD" />
            </div>
          </div>
        </section>

        <section class="group">
          <div class="group-title">固定端</div>
          <div class="grid2">
            <div class="field">
              <label>固定利率 %</label>
              <div class="inline">
                <el-input-number v-model="form.fixedRate" :step="0.01" :precision="6" :controls="false" />
                <el-button :loading="parLoading" @click="onParRate">计算平价</el-button>
              </div>
            </div>
            <div class="field">
              <label>付息频率</label>
              <el-select v-model="form.fixedFreqMonths">
                <el-option :value="3" label="季度" />
                <el-option :value="12" label="年度" />
              </el-select>
            </div>
          </div>
        </section>

        <section class="group">
          <div class="group-title">浮动端</div>
          <div class="field">
            <label>利差 bp(叠加在基准之上)</label>
            <el-input-number v-model="form.spread" :step="1" :precision="2" :controls="false" />
          </div>
        </section>

        <section class="group">
          <div class="group-title">估值与归因</div>
          <div class="grid2">
            <div class="field">
              <label>估值日 T</label>
              <el-date-picker v-model="form.valuationDate" type="date" value-format="YYYY-MM-DD" />
            </div>
            <div class="field">
              <label>归因起始日 t0</label>
              <el-date-picker v-model="form.startDate" type="date" value-format="YYYY-MM-DD"
                              placeholder="选填 默认上一交易日" />
            </div>
          </div>
          <div class="grid2" style="margin-top: 12px">
            <div class="field">
              <label>贴现口径</label>
              <el-radio-group v-model="form.discountBasis" class="seg">
                <el-radio-button value="simple">单利</el-radio-button>
                <el-radio-button value="cont">连续复利</el-radio-button>
              </el-radio-group>
            </div>
          </div>
          <div class="grid2" style="margin-top: 12px">
            <div class="field">
              <label>曲线插值</label>
              <el-radio-group v-model="curveInterp" class="seg">
                <el-radio-button value="linear">线性</el-radio-button>
                <el-radio-button value="hermite">Hermite</el-radio-button>
              </el-radio-group>
            </div>
          </div>
          <div class="hint" style="margin-top: 4px">
            插值作用于整条定价曲线:贴现与浮动端未来重置利率预测均随之变化(NPV/DV01 受影响);线性 = 零利率线性(默认口径),切换后需重新「计算估值」
          </div>
          <div class="field" style="margin-top: 12px">
            <el-checkbox v-model="form.principalExchange">本金交割(到期两腿互换名义,不含首期)</el-checkbox>
          </div>
          <div class="hint">
            默认取上一交易日(T-1)至 T 归因;估值日无完整行情(非交易日或超出行情数据覆盖)时结果为 0<br>
            未修改曲线时自动取 t0/t1 两日行情;修改右侧曲线后按该曲线归因(两日同形则曲线效应为 0)
          </div>
          <div class="hint">
            统一口径:定盘取值固定当日(重置日当日上午定盘已发布);曲线自动补 7D 锚点行 = 当期定盘,为普通可编辑行,重新加载行情时按新定盘重建
          </div>
        </section>

        <div class="actions">
          <el-button type="primary" plain :loading="loadingMarket" @click="onLoadMarket">加载行情</el-button>
          <el-button type="primary" :loading="loadingValue" @click="onValue">计算估值</el-button>
          <el-button type="success" :loading="loadingAttr" @click="onAttribution">计算归因</el-button>
        </div>
      </aside>

      <!-- 右:展示区 -->
      <main class="display-panel">
        <el-card v-if="warnings.length" shadow="never" class="block-card">
          <el-alert v-for="(w, i) in warnings" :key="i" :title="w" type="warning"
                    :closable="false" style="margin-bottom: 4px" />
        </el-card>

        <el-card v-if="valueResult" shadow="never" class="block-card">
          <template #header><span class="card-title">估值结果</span></template>
          <el-row :gutter="12">
            <el-col :span="6"><stat-card title="NPV(元)" :v="valueResult.npv" /></el-col>
            <el-col :span="6"><stat-card title="固定腿 PV(元)" :v="valueResult.pv_fixed" /></el-col>
            <el-col :span="6"><stat-card title="浮动腿 PV(元)" :v="valueResult.pv_floating" /></el-col>
            <el-col :span="6"><stat-card title="平行 DV01(元/bp)" :v="valueResult.dv01_parallel" /></el-col>
          </el-row>
        </el-card>

        <el-tabs v-model="activeTab" class="result-tabs">
          <el-tab-pane label="市场曲线" name="curve">
            <el-alert v-if="marketApprox" type="warning" :closable="false"
                      title="当前日期在交易日历数据范围之外,日历按周末规则近似" style="margin-bottom: 8px" />
            <div class="curve-layout">
              <div class="curve-left">
                <el-table :data="curveRows" size="small" style="width: 100%">
                  <template #empty>
                    <span class="muted">点击左侧「加载行情」载入估值日曲线</span>
                  </template>
                  <el-table-column prop="tenor" label="期限" width="90" />
                  <el-table-column label="零息利率 %">
                    <template #default="{ row }">
                      <el-input-number v-model="row.rate" :precision="4" :controls="false"
                                       size="small" style="width: 120px" />
                    </template>
                  </el-table-column>
                </el-table>
                <div v-if="fixingInfo" class="fixing-chip muted">
                  当期定盘 {{ benchLabel }} {{ fixingInfo.date }} = <b>{{ fixingInfo.rate }}%</b>
                </div>
              </div>
              <div class="curve-right">
                <div v-if="!curveChart.pts.length" class="muted curve-empty">
                  加载行情后显示收益率曲线
                </div>
                <div v-else class="curve-chart" @pointerleave="hoverIdx = null">
                  <svg :viewBox="`0 0 ${CHART_W} ${CHART_H}`" width="100%" tabindex="0"
                       role="img" aria-label="零息收益率曲线"
                       @pointermove="onChartMove" @keydown="onChartKey">
                    <text class="chart-title" :x="PAD.l" :y="12">
                      零息收益率曲线 · {{ benchLabel }} · {{ form.valuationDate }}
                    </text>
                    <line v-for="t in curveChart.yTicks" :key="`g${t.v}`"
                          :x1="PAD.l" :x2="CHART_W - PAD.r" :y1="t.y" :y2="t.y"
                          stroke="#2c2c2a" stroke-width="1" />
                    <line :x1="PAD.l" :x2="CHART_W - PAD.r" :y1="CHART_H - PAD.b"
                          :y2="CHART_H - PAD.b" stroke="#383835" stroke-width="1" />
                    <text v-for="t in curveChart.yTicks" :key="`y${t.v}`" class="axis-text"
                          :x="PAD.l - 6" :y="t.y + 3" text-anchor="end">{{ t.v.toFixed(2) }}</text>
                    <text v-for="p in curveChart.ticks" :key="`x${p.tenor}`" class="axis-text"
                          :x="p.x" :y="CHART_H - PAD.b + 14" text-anchor="middle">{{ p.tenor }}</text>
                    <line v-if="hoverIdx != null" :x1="curveChart.pts[hoverIdx].x"
                          :x2="curveChart.pts[hoverIdx].x" :y1="PAD.t" :y2="CHART_H - PAD.b"
                          stroke="#383835" stroke-width="1" />
                    <polyline :points="curveChart.path" fill="none" stroke="#3987e5"
                              stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
                    <circle v-if="hoverIdx != null" :cx="curveChart.pts[hoverIdx].x"
                            :cy="curveChart.pts[hoverIdx].y" r="4" fill="#3987e5"
                            stroke="var(--el-bg-color)" stroke-width="2" />
                    <circle v-if="curveChart.pts.length"
                            :cx="curveChart.pts[curveChart.pts.length - 1].x"
                            :cy="curveChart.pts[curveChart.pts.length - 1].y" r="4" fill="#3987e5"
                            stroke="var(--el-bg-color)" stroke-width="2" />
                    <text v-if="curveChart.pts.length" class="curve-lbl" text-anchor="end"
                          :x="curveChart.pts[curveChart.pts.length - 1].x + 2"
                          :y="curveChart.pts[curveChart.pts.length - 1].y - 10">
                      {{ curveChart.pts[curveChart.pts.length - 1].rate.toFixed(4) }}%
                    </text>
                    <g v-if="curveChart.fpt">
                      <circle :cx="curveChart.fpt.x" :cy="curveChart.fpt.y" r="4.5"
                              fill="#d95926" stroke="var(--el-bg-color)" stroke-width="2" />
                      <text class="curve-lbl" :text-anchor="curveChart.fpt.x > CHART_W - 100 ? 'end' : 'start'"
                            :x="curveChart.fpt.x + (curveChart.fpt.x > CHART_W - 100 ? -9 : 9)"
                            :y="curveChart.fpt.y - 9">
                        定盘 {{ fixingInfo.rate }}%
                      </text>
                    </g>
                  </svg>
                  <div v-if="hoverIdx != null" class="curve-tip"
                       :class="tipClass" :style="tipStyle">
                    <div class="tip-val">{{ curveChart.pts[hoverIdx].rate.toFixed(4) }}%</div>
                    <div class="tip-key"><span class="key-line"></span>{{ benchLabel }} {{ curveChart.pts[hoverIdx].lbl }}</div>
                  </div>
                </div>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="关键期限 DV01" name="krdv">
            <el-table v-if="valueResult" :data="valueResult.krdv01" size="small">
              <template #empty>
                <span class="muted">剩余期限不足最小期限点,DV01 不适用</span>
              </template>
              <el-table-column prop="tenor" label="期限" width="90" />
              <el-table-column prop="dv01" label="KRDV01(元/bp)">
                <template #default="{ row }">{{ fmt(row.dv01) }}</template>
              </el-table-column>
            </el-table>
            <div v-if="valueResult" class="muted" style="margin-top: 6px">
              合计 = {{ fmt(krdvSum) }};≈ 平行 DV01
            </div>
          </el-tab-pane>

          <el-tab-pane label="现金流明细" name="cf">
            <template v-if="valueResult">
              <h4 class="section-h">固定腿</h4>
              <el-table :data="valueResult.cashflows.fixed" size="small" border>
                <el-table-column prop="pay_date" label="支付日" width="110" />
                <el-table-column prop="accrual_start" label="计息起" width="110" />
                <el-table-column prop="accrual_end" label="计息止" width="110" />
                <el-table-column prop="days" label="天数" width="70" />
                <el-table-column prop="rate" label="利率 %">
                  <template #default="{ row }">{{ row.rate.toFixed(4) }}</template>
                </el-table-column>
                <el-table-column label="现金流(元)">
                  <template #default="{ row }">{{ fmt(row.amount) }}</template>
                </el-table-column>
                <el-table-column label="DF">
                  <template #default="{ row }">{{ row.df.toFixed(6) }}</template>
                </el-table-column>
                <el-table-column label="现值(元)">
                  <template #default="{ row }">{{ fmt(row.pv) }}</template>
                </el-table-column>
              </el-table>
              <h4 class="section-h" style="margin-top:16px">浮动腿(展开行查看重置子区间)</h4>
              <el-table :data="valueResult.cashflows.floating" size="small" border row-key="pay_date">
                <el-table-column type="expand">
                  <template #default="{ row }">
                    <el-table :data="row.sub_periods" size="small">
                      <el-table-column prop="reset_date" label="重置日" width="110" />
                      <el-table-column prop="accrual_start" label="起" width="110" />
                      <el-table-column prop="accrual_end" label="止" width="110" />
                      <el-table-column prop="days" label="天数" width="70" />
                      <el-table-column label="利率 %">
                        <template #default="{ row: sp }">{{ sp.rate.toFixed(4) }}</template>
                      </el-table-column>
                      <el-table-column prop="source" label="来源" width="90" />
                    </el-table>
                  </template>
                </el-table-column>
                <el-table-column prop="pay_date" label="支付日" width="110" />
                <el-table-column prop="days" label="天数" width="70" />
                <el-table-column label="利率 %">
                  <template #default="{ row }">{{ row.rate.toFixed(4) }}</template>
                </el-table-column>
                <el-table-column label="现金流(元)">
                  <template #default="{ row }">{{ fmt(row.amount) }}</template>
                </el-table-column>
                <el-table-column label="DF">
                  <template #default="{ row }">{{ row.df.toFixed(6) }}</template>
                </el-table-column>
                <el-table-column label="现值(元)">
                  <template #default="{ row }">{{ fmt(row.pv) }}</template>
                </el-table-column>
              </el-table>
            </template>
          </el-tab-pane>

          <el-tab-pane label="Campisi 归因" name="attr" :disabled="!attributionResult">
            <template v-if="attributionResult">
              <el-row :gutter="12" style="margin-bottom: 12px">
                <el-col :span="6"><stat-card title="全价损益 ΔNPV" :v="attributionResult.delta_npv" /></el-col>
                <el-col :span="6"><stat-card title="区间现金流 CF" :v="attributionResult.cf" /></el-col>
                <el-col :span="6">
                  <el-card shadow="never">
                    <div class="muted" style="font-size:13px">勾稽校验</div>
                    <div :style="{ color: attributionResult.identity.ok ? '#3dbf9b' : '#e05252', fontSize: '18px', fontWeight: 600 }">
                      {{ attributionResult.identity.ok ? '通过' : '失败' }}
                      (差 {{ attributionResult.identity.diff === 0 ? '0'
                            : attributionResult.identity.diff.toExponential(2) }})
                    </div>
                  </el-card>
                </el-col>
              </el-row>
              <el-table :data="attrRows" size="small" border>
                <el-table-column prop="label" label="分项" width="220" />
                <el-table-column label="金额(元)" align="right">
                  <template #default="{ row }">
                    <span :style="{ color: pnlColor(row.value) }">{{ fmt(row.value) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="含义" />
              </el-table>
              <h4 class="section-h" style="margin-top:16px">曲线效应明细</h4>
              <el-table :data="attributionResult.detail" size="small" border>
                <el-table-column prop="tenor" label="期限" width="90" />
                <el-table-column label="Δy(bp)" align="right">
                  <template #default="{ row }">{{ row.dy_bp.toFixed(2) }}</template>
                </el-table-column>
                <el-table-column label="KRDV01(元/bp)" align="right">
                  <template #default="{ row }">{{ fmt(row.krdv01) }}</template>
                </el-table-column>
                <el-table-column label="贡献(元)" align="right">
                  <template #default="{ row }">
                    <span :style="{ color: pnlColor(row.contribution) }">{{ fmt(row.contribution) }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </template>
          </el-tab-pane>
        </el-tabs>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onMounted, ref, watch } from 'vue'
import { ElCard, ElMessage } from 'element-plus'
import { loadMarket, postAttribution, postParRate, postValue } from '../api/client'

const StatCard = defineComponent({
  props: { title: String, v: Number },
  setup(props) {
    // h() 的字符串标签不会解析全局注册组件(只走原生 createElement),必须传组件对象
    return () => h(ElCard, { shadow: 'never' }, () => [
      h('div', { class: 'muted', style: 'font-size:13px' }, props.title),
      // 终端配色(参考设计):正数红、负数绿、零与空值中性
      h('div', {
        style: `font-size:20px;font-weight:600;color:${pnlColor(props.v)}`,
      }, formatNumber(props.v)),
    ])
  },
})

function pnlColor(v) {
  if (v == null || Number.isNaN(v) || v === 0 || Object.is(v, -0)) return 'var(--irs-text)'
  return v > 0 ? '#e05252' : '#3dbf9b'
}

function formatNumber(v) {
  if (v == null || Number.isNaN(v)) return '-'
  if (Object.is(v, -0)) v = 0  // 负零归一化,避免明细里出现 "-0.00"
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const form = ref({
  benchmark: 'FR007', direction: 'receiver', notional: 100000000,
  fixedRate: 1.65, spread: 0.0,  // 浮动端利差,单位 bp(与 API spread_bp 同口径)
  effectiveDate: '2026-06-01', maturityDate: '2029-06-01',
  fixedFreqMonths: 3, valuationDate: '2026-11-06', startDate: '',
  discountBasis: 'cont', principalExchange: true,  // 定盘取值固定当日,见 payload 里 fixing_lag_bd
})
const curveRows = ref([])
let marketCurveSnapshot = null  // 最近一次加载行情的曲线快照(深拷贝,刻意不用响应式)
const fixingInfo = ref(null)
const marketApprox = ref(false)
const loadingMarket = ref(false)
const loadingValue = ref(false)
const loadingAttr = ref(false)
const valueResult = ref(null)
const attributionResult = ref(null)
const warnings = ref([])
const activeTab = ref('curve')

const fmt = formatNumber
const krdvSum = computed(() =>
  valueResult.value ? valueResult.value.krdv01.reduce((s, x) => s + x.dv01, 0) : 0)

const benchLabel = computed(() => form.value.benchmark === 'FR007' ? 'FR007' : 'Shibor 3M')

// —— 收益率曲线图(左表右图;暗色 token:网格 #2c2c2a / 轴 #383835 / 轴字 #898781 /
//    序列蓝 #3987e5 / 定盘橙 #d95926,均为 dataviz 暗色档已验证值)——
const CHART_W = 640, CHART_H = 300
const PAD = { l: 48, r: 30, t: 16, b: 34 }
const hoverIdx = ref(null)
// 曲线插值(定价参数,控件在左侧参数区):linear = 零利率线性(默认);
// hermite = 单调三次,内核贴现与浮动端重置利率预测均用之,切换后需重新「计算估值」;图随所选口径绘制
const curveInterp = ref('linear')

function tenorDays(tenor) {
  const m = /^(\d+)\s*([DdMmYy])$/.exec(String(tenor ?? '').trim())
  if (!m) return NaN
  const n = +m[1]
  return /D/i.test(m[2]) ? n : /M/i.test(m[2]) ? n * 30.4375 : n * 365.25
}

function daysLabel(d) {
  return d < 365.25 ? `${Math.round(d)}D` : `${(d / 365.25).toFixed(2)}Y`
}

const curveChart = computed(() => {
  const raw = curveRows.value
    .filter(r => r.tenor && Number.isFinite(+r.rate))
    .map(r => ({ tenor: String(r.tenor).trim().toUpperCase(), rate: +r.rate, days: tenorDays(r.tenor) }))
    .filter(p => Number.isFinite(p.days))
    .sort((a, b) => a.days - b.days)
  const fx = fixingInfo.value && Number.isFinite(+fixingInfo.value.rate)
    ? { days: 7, rate: +fixingInfo.value.rate } : null
  if (!raw.length) return { pts: [], ticks: [], fpt: null, yTicks: [], path: '' }

  let lo = Math.min(...raw.map(p => p.rate)), hi = Math.max(...raw.map(p => p.rate))
  if (fx) { lo = Math.min(lo, fx.rate); hi = Math.max(hi, fx.rate) }
  if (hi - lo < 1e-9) { lo -= 0.05; hi += 0.05 }
  const pad = (hi - lo) * 0.12; lo -= pad; hi += pad
  const W = CHART_W - PAD.l - PAD.r, H = CHART_H - PAD.t - PAD.b
  const d0 = fx ? Math.min(fx.days, raw[0].days) : raw[0].days
  const d1 = raw.length > 1 ? raw[raw.length - 1].days : d0 + 1
  const xOf = (d) => PAD.l + (d - d0) / (d1 - d0) * W
  const yOf = (r) => PAD.t + (hi - r) / (hi - lo) * H

  // 采样插值与左侧「曲线插值」参数同一口径,均严格穿过全部报价点,图 = 定价所用曲线:
  // - 线性(默认):与后端 ZeroCurve 同法、两端平推
  // - Hermite:单调三次(Fritsch–Carlson),与内核 _hermite_tangents 同法,
  //   节点切线连续、无过冲,端部切线取 0 与平推衔接(与中债曲线同族)
  const nQ = raw.length
  let zeroAt
  if (curveInterp.value === 'hermite') {
    const del = []
    for (let i = 0; i < nQ - 1; i++)
      del.push((raw[i + 1].rate - raw[i].rate) / (raw[i + 1].days - raw[i].days))
    const tan = raw.map(() => 0)
    for (let i = 1; i < nQ - 1; i++) {
      if (del[i - 1] * del[i] <= 0) continue // 局部极值点切线取 0,防止过冲
      const h0 = raw[i].days - raw[i - 1].days
      const h1 = raw[i + 1].days - raw[i].days
      const w1 = 2 * h1 + h0, w2 = h1 + 2 * h0
      tan[i] = (w1 + w2) / (w1 / del[i - 1] + w2 / del[i])
    }
    zeroAt = (d) => {
      if (d <= raw[0].days) return raw[0].rate
      if (d >= raw[nQ - 1].days) return raw[nQ - 1].rate
      let i = 0
      while (i < nQ - 2 && d > raw[i + 1].days) i++
      const a = raw[i], b = raw[i + 1], h = b.days - a.days
      const t = (d - a.days) / h, t2 = t * t, t3 = t2 * t
      return (2 * t3 - 3 * t2 + 1) * a.rate + (t3 - 2 * t2 + t) * h * tan[i]
           + (-2 * t3 + 3 * t2) * b.rate + (t3 - t2) * h * tan[i + 1]
    }
  } else {
    zeroAt = (d) => {
      if (d <= raw[0].days) return raw[0].rate
      if (d >= raw[nQ - 1].days) return raw[nQ - 1].rate
      for (let i = 0; i < nQ - 1; i++) {
        if (d <= raw[i + 1].days) {
          const w = (d - raw[i].days) / (raw[i + 1].days - raw[i].days)
          return raw[i].rate + (raw[i + 1].rate - raw[i].rate) * w
        }
      }
      return raw[nQ - 1].rate
    }
  }
  const lblOf = (d) => {
    const a = raw.find(p => Math.abs(p.days - d) < 0.01)
    return a ? a.tenor : daysLabel(d)
  }

  // 按基准的重置周期细采样(FR007 每周 / Shibor 3M 每季)替代报价点直连,逐点取所选插值
  const stepDays = form.value.benchmark === 'FR007' ? 7 : 3 * 30.4375
  const sampled = [{ d: d0, rate: zeroAt(d0) }]
  if (d1 > d0 + 1e-9) {
    for (let d = d0 + stepDays; d < d1 - 1e-9; d += stepDays) sampled.push({ d, rate: zeroAt(d) })
    if (d1 - sampled[sampled.length - 1].d > 1e-6) sampled.push({ d: d1, rate: zeroAt(d1) })
  }
  const pts = sampled.map(p => ({
    days: p.d, rate: p.rate, lbl: lblOf(p.d), x: xOf(p.d), y: yOf(p.rate),
  }))
  // x 轴刻度取报价期限点;按估算文字宽度避让,短端过密时跳过,首末刻度必显
  const estW = (s) => s.length * 7.2 + 4
  const gapOk = (a, b) => b.x - a.x >= (estW(a.tenor) + estW(b.tenor)) / 2 + 8
  const ticks = []
  let prevTick = null
  raw.forEach((p, i) => {
    const t = { tenor: p.tenor, x: xOf(p.days) }
    const isLast = i === raw.length - 1
    if (isLast) {
      while (prevTick && !gapOk(prevTick, t)) {
        ticks.pop()
        prevTick = ticks[ticks.length - 1] || null
      }
      ticks.push(t)
      return
    }
    if (!prevTick || gapOk(prevTick, t)) { ticks.push(t); prevTick = t }
  })
  const fpt = fx ? { x: xOf(fx.days), y: yOf(fx.rate) } : null
  // nice 刻度:1/2/5×10^k,约 5~7 格,保证曲线最低点下方也落有刻度(直接携带 y 坐标,模板免再算)
  const span = hi - lo, mag = 10 ** Math.floor(Math.log10(span / 5))
  const nrm = span / 5 / mag
  const step = (nrm >= 5 ? 5 : nrm >= 2 ? 2 : 1) * mag
  const yTicks = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) {
    yTicks.push({ v: +v.toFixed(8), y: PAD.t + (hi - v) / (hi - lo) * H })
  }
  return {
    pts, ticks, fpt, yTicks,
    path: pts.map(p => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' '),
  }
})

const tipStyle = computed(() => {
  if (hoverIdx.value == null) return {}
  const p = curveChart.value.pts[hoverIdx.value]
  return { left: (p.x / CHART_W * 100) + '%', top: (p.y / CHART_H * 100) + '%' }
})
const tipClass = computed(() => {
  if (hoverIdx.value == null) return ''
  const p = curveChart.value.pts[hoverIdx.value]
  return p.x < CHART_W * 0.15 ? 'edge-l' : p.x > CHART_W * 0.85 ? 'edge-r' : ''
})

function onChartMove(e) {
  const { pts } = curveChart.value
  if (!pts.length) { hoverIdx.value = null; return }
  const rect = e.currentTarget.getBoundingClientRect()
  const x = (e.clientX - rect.left) / rect.width * CHART_W
  let best = 0, bd = Infinity
  pts.forEach((p, i) => { const d = Math.abs(p.x - x); if (d < bd) { bd = d; best = i } })
  hoverIdx.value = best
}

function onChartKey(e) {
  const n = curveChart.value.pts.length
  if (!n) return
  if (e.key === 'ArrowRight') {
    hoverIdx.value = hoverIdx.value == null ? 0 : Math.min(n - 1, hoverIdx.value + 1)
    e.preventDefault()
  } else if (e.key === 'ArrowLeft') {
    hoverIdx.value = hoverIdx.value == null ? n - 1 : Math.max(0, hoverIdx.value - 1)
    e.preventDefault()
  } else if (e.key === 'Escape') {
    hoverIdx.value = null
  }
}

const attrRows = computed(() => {
  const a = attributionResult.value
  if (!a) return []
  const c = a.components
  return [
    { label: '时间效应 Θ(其中:)', value: c.theta },
    { label: '  票息效应 Carry', value: c.carry },
    { label: '  骑乘效应 Roll-down', value: c.roll },
    { label: '曲线效应 Curve', value: c.curve },
    { label: '利差效应 Spread', value: c.spread },
    { label: '残差 ε', value: c.residual },
  ]
})

function payload() {
  return {
    benchmark: form.value.benchmark,
    direction: form.value.direction,
    notional: form.value.notional,
    fixed_rate: form.value.fixedRate,
    spread_bp: form.value.spread,  // bp,与输入框同单位,不做换算
    effective_date: form.value.effectiveDate,
    maturity_date: form.value.maturityDate,
    fixed_freq_months: form.value.fixedFreqMonths,
    valuation_date: form.value.valuationDate,
    curve: curveRows.value.map(r => ({ tenor: r.tenor, rate: r.rate })),
    fixing_overrides: {},
    discount_basis: form.value.discountBasis,
    curve_interp: curveInterp.value,
    fixing_lag_bd: 0,  // 统一口径:当日定盘(厂商的 T-1 取法仅保留在 API 参数与后端测试中)
    principal_exchange: form.value.principalExchange,
  }
}

// 统一口径:曲线缺 7D 锚点行时注入 7D=当期定盘(FR007 定盘本身即 7 天回购利率,期限匹配;
// 仅影响首个报价期限之前的曲线段)。注入行为普通可编辑行,重新加载行情时按新定盘重建
function injectSevenDayAnchor() {
  if (!curveRows.value.length || curveRows.value.some(r => r.tenor === '7D')) return
  const f = fixingInfo.value?.rate
  const rate = f != null && Number.isFinite(+f) ? +f : curveRows.value[0].rate
  curveRows.value.unshift({ tenor: '7D', rate })
}

// 归因曲线模式:表内曲线与加载行情时的快照逐行一致(或表内为空)→ 发空曲线,
// 后端按 t0/t1 两日行情各自加载(真实两日位移能算出非零曲线效应);
// 用户改过表内曲线 → 仍发显式行(两日同形则曲线效应为 0,属该模式的文档化语义)
function attributionCurve() {
  if (!curveRows.value.length) return []
  if (marketCurveSnapshot != null &&
      JSON.stringify(curveRows.value) === JSON.stringify(marketCurveSnapshot)) {
    return []
  }
  return curveRows.value.map(r => ({ tenor: r.tenor, rate: r.rate }))
}

function errText(e) {
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map(x => `${x.msg}(${(x.loc || []).slice(1).join('.')})`).join('; ')
  return `请求失败(${e?.response?.status ?? e?.message ?? '未知错误'})`
}

// 固定利率默认跟随当期定盘;用户手动改过之后不再自动覆盖
let fixedRateTouched = false
let suppressFixedRateWatch = false
watch(() => form.value.fixedRate, () => {
  if (!suppressFixedRateWatch) fixedRateTouched = true
})

function syncFixedRateToFixing() {
  const r = fixingInfo.value?.rate
  if (!fixedRateTouched && r != null && Number.isFinite(+r)) {
    suppressFixedRateWatch = true
    form.value.fixedRate = +r
    nextTick(() => { suppressFixedRateWatch = false })
  }
}

// 进入页面自动加载行情(固定利率同步取当期定盘)
onMounted(() => { onLoadMarket() })

async function onLoadMarket() {
  loadingMarket.value = true
  try {
    const m = await loadMarket(form.value.benchmark, form.value.valuationDate)
    curveRows.value = m.curve.map(x => ({ ...x }))
    fixingInfo.value = m.fixing
    injectSevenDayAnchor()
    marketCurveSnapshot = JSON.parse(JSON.stringify(curveRows.value))  // 快照含 7D 注入行
    syncFixedRateToFixing()
    marketApprox.value = m.calendar_approximate
    valueResult.value = null
    attributionResult.value = null
    warnings.value = []  // 新行情下旧告警必失效,随结果一并清空
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    loadingMarket.value = false
  }
}

async function onValue() {
  loadingValue.value = true
  try {
    valueResult.value = await postValue(payload())
    warnings.value = valueResult.value.warnings || []
    attributionResult.value = null
    activeTab.value = 'krdv'
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    loadingValue.value = false
  }
}

async function onAttribution() {
  loadingAttr.value = true
  try {
    // t0 留空发 null → 后端默认窗口(行情中 T-1 = max(d<T));T 非交易日返回全零 + 告警
    const p = { ...payload(), start_date: form.value.startDate || null, curve: attributionCurve() }
    attributionResult.value = await postAttribution(p)
    warnings.value = attributionResult.value.warnings || []
    activeTab.value = 'attr'
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    loadingAttr.value = false
  }
}

// 平价利率:使 NPV=0 的固定利率;与当前曲线/利差/日期口径一致,成功后回填输入框
const parLoading = ref(false)
async function onParRate() {
  parLoading.value = true
  try {
    const r = await postParRate(payload())
    form.value.fixedRate = Math.round(r.par_rate * 1e6) / 1e6   // 6 位小数(百分数),舍入残差上界 = 年金×5e-9
    ElMessage.success(`平价利率 ${r.par_rate.toFixed(6)}%,已回填固定利率(重新「计算估值」应得 NPV≈0)`)
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    parLoading.value = false
  }
}
</script>

<style scoped>
.page {
  --irs-bg: #161a22;
  --irs-panel: #1e222c;
  --irs-border: #2a2f3a;
  --irs-text: #e8eaed;
  --irs-muted: #8a919e;
  --irs-orange: #e07040;
  min-height: 100vh;
  background: var(--irs-bg);
  color: var(--irs-text);
  font-size: 14px;
}

.topbar {
  height: 48px;
  background: var(--irs-panel);
  border-bottom: 1px solid var(--irs-border);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 20px;
}
.brand-sq {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  background: linear-gradient(135deg, #1c3d5e, #3b7ddd);
}
.brand { font-size: 15px; font-weight: 600; }
.brand-sub { font-size: 12px; color: var(--irs-muted); }

.layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  max-width: 1440px;
  margin: 0 auto;
  padding: 16px;
}

/* ---- 左:输入区 ---- */
.input-panel {
  width: 400px;
  flex: none;
  background: var(--irs-panel);
  border: 1px solid var(--irs-border);
  border-radius: 8px;
  padding: 16px;
}
.swap-bar {
  background: linear-gradient(135deg, #1c3d5e, #2b6cb0);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 16px;
}
.group { margin-bottom: 16px; }
.group-title {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: var(--irs-muted);
  margin-bottom: 10px;
}
.group-title::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 1px;
  background: var(--irs-orange);
  margin-right: 6px;
}
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.field label {
  display: block;
  font-size: 12px;
  color: var(--irs-muted);
  margin-bottom: 4px;
}
.field :deep(.el-input-number),
.field :deep(.el-select),
.field :deep(.el-date-editor) { width: 100%; }
.field .inline { display: flex; gap: 8px; align-items: center; }
.field .inline :deep(.el-button) { flex: none; }
.seg :deep(.el-radio-button__inner) { padding: 7px 12px; width: 100%; }
.hint {
  font-size: 12px;
  line-height: 1.7;
  color: var(--irs-muted);
  margin-top: 10px;
}
.actions { display: flex; gap: 8px; }
.actions :deep(.el-button) { flex: 1; margin-left: 0; }

/* ---- 右:展示区 ---- */
.display-panel { flex: 1; min-width: 0; }
.block-card { margin-bottom: 12px; }
.card-title { font-size: 13px; color: var(--irs-orange); font-weight: 600; }
.muted { color: var(--irs-muted); }
.section-h { color: var(--irs-text); margin: 8px 0; font-size: 14px; }
.result-tabs :deep(.el-tabs__item) { font-size: 14px; }

/* —— 市场曲线:左表右图 —— */
.curve-layout { display: flex; gap: 20px; align-items: stretch; flex-wrap: wrap; }
.curve-left { width: 300px; flex: none; }
.curve-right { flex: 1; min-width: 340px; display: flex; align-items: center; justify-content: center; }
.curve-empty { height: 220px; display: flex; align-items: center; justify-content: center; }
.curve-chart { position: relative; width: 100%; max-width: 760px; }
.curve-chart svg { display: block; outline: none; cursor: crosshair; }
.curve-chart svg:focus-visible { outline: 1px solid var(--el-color-primary); outline-offset: 2px; }
.chart-title { font-size: 12px; fill: var(--irs-text); }
.axis-text { font-size: 11px; fill: #898781; font-variant-numeric: tabular-nums; }
.curve-lbl { font-size: 11px; fill: #c3c2b7; font-variant-numeric: tabular-nums; }
.curve-tip {
  position: absolute; pointer-events: none; z-index: 5; white-space: nowrap;
  background: #1f1f1e; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px;
  padding: 6px 10px; transform: translate(-50%, -120%);
}
.curve-tip.edge-l { transform: translate(0, -120%); }
.curve-tip.edge-r { transform: translate(-100%, -120%); }
.tip-val { font-size: 14px; font-weight: 600; color: #f0efec; font-variant-numeric: tabular-nums; }
.tip-key { font-size: 11px; color: #c3c2b7; margin-top: 2px; display: flex; align-items: center; gap: 6px; }
.key-line { display: inline-block; width: 12px; height: 2px; background: #3987e5; border-radius: 1px; }
.fixing-chip { margin-top: 8px; }
.fixing-chip b { color: var(--irs-text); }

@media (max-width: 1100px) {
  .layout { flex-direction: column; }
  .input-panel { width: auto; }
}
</style>
