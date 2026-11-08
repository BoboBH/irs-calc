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
              <el-input-number v-model="form.fixedRate" :step="0.01" :precision="4" :controls="false" />
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
            <label>利差 %(叠加在基准之上)</label>
            <el-input-number v-model="form.spread" :step="0.0001" :precision="4" :controls="false" />
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
            <div class="field">
              <label>定盘取值</label>
              <el-radio-group v-model="form.fixingLagBd" class="seg">
                <el-radio-button :value="0">当日</el-radio-button>
                <el-radio-button :value="1">T-1 营业日</el-radio-button>
              </el-radio-group>
            </div>
          </div>
          <div class="field" style="margin-top: 12px">
            <el-checkbox v-model="form.principalExchange">本金交割(到期两腿互换名义,不含首期)</el-checkbox>
          </div>
          <div class="hint">
            默认取上一交易日(T-1)至 T 归因;估值日无完整行情(非交易日或超出行情数据覆盖)时结果为 0<br>
            未修改曲线时自动取 t0/t1 两日行情;修改右侧曲线后按该曲线归因(两日同形则曲线效应为 0)
          </div>
          <div class="actions" style="margin-top: 8px">
            <el-button size="small" @click="applyVendorPreset">对齐厂商口径</el-button>
            <el-button size="small" @click="applyDefaultConvention">恢复默认口径</el-button>
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
            <div v-if="fixingInfo" class="muted" style="margin-top: 8px">
              当期定盘:{{ form.benchmark === 'FR007' ? 'FR007' : 'Shibor 3M' }}
              {{ fixingInfo.date }} = {{ fixingInfo.rate }}%
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
import { computed, defineComponent, h, ref } from 'vue'
import { ElCard, ElMessage } from 'element-plus'
import { loadMarket, postAttribution, postValue } from '../api/client'

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
  fixedRate: 1.65, spread: 0.0,
  effectiveDate: '2026-06-01', maturityDate: '2026-12-01',
  fixedFreqMonths: 3, valuationDate: '2026-11-06', startDate: '',
  discountBasis: 'simple', fixingLagBd: 0, principalExchange: false,
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
    spread: form.value.spread,
    effective_date: form.value.effectiveDate,
    maturity_date: form.value.maturityDate,
    fixed_freq_months: form.value.fixedFreqMonths,
    valuation_date: form.value.valuationDate,
    curve: curveRows.value.map(r => ({ tenor: r.tenor, rate: r.rate })),
    fixing_overrides: {},
    discount_basis: form.value.discountBasis,
    fixing_lag_bd: form.value.fixingLagBd,
    principal_exchange: form.value.principalExchange,
  }
}

// 厂商口径预设:连续复利 + T-1 定盘 + 本金交割;曲线缺 7D 锚点行时按当期定盘补一行
function applyVendorPreset() {
  form.value.discountBasis = 'cont'
  form.value.fixingLagBd = 1
  form.value.principalExchange = true
  if (curveRows.value.length && !curveRows.value.some(r => r.tenor === '7D')) {
    const anchorRate = fixingInfo.value ? fixingInfo.value.rate : curveRows.value[0].rate
    curveRows.value.unshift({ tenor: '7D', rate: anchorRate })
  }
}

function applyDefaultConvention() {
  form.value.discountBasis = 'simple'
  form.value.fixingLagBd = 0
  form.value.principalExchange = false
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

async function onLoadMarket() {
  loadingMarket.value = true
  try {
    const m = await loadMarket(form.value.benchmark, form.value.valuationDate)
    curveRows.value = m.curve.map(x => ({ ...x }))
    marketCurveSnapshot = JSON.parse(JSON.stringify(curveRows.value))
    fixingInfo.value = m.fixing
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

@media (max-width: 1100px) {
  .layout { flex-direction: column; }
  .input-panel { width: auto; }
}
</style>
