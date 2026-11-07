<template>
  <el-container style="max-width: 1280px; margin: 0 auto; padding: 16px">
    <el-main>
      <h2>利率互换计算器</h2>

      <!-- ① 合约信息 -->
      <el-card header="① 合约信息" shadow="never" style="margin-bottom: 12px">
        <el-form :model="form" inline label-width="110px">
          <el-form-item label="基准利率">
            <el-select v-model="form.benchmark" style="width: 140px">
              <el-option value="FR007" label="FR007" />
              <el-option value="SHIBOR3M" label="SHIBOR 3M" />
            </el-select>
          </el-form-item>
          <el-form-item label="头寸方向">
            <el-select v-model="form.direction" style="width: 140px">
              <el-option value="receiver" label="收固定" />
              <el-option value="payer" label="付固定" />
            </el-select>
          </el-form-item>
          <el-form-item label="名义本金">
            <el-input-number v-model="form.notional" :min="1" :step="10000000"
                             :controls="false" style="width: 160px" />
          </el-form-item>
          <el-form-item label="固定利率 %">
            <el-input-number v-model="form.fixedRate" :step="0.01" :precision="4"
                             :controls="false" style="width: 120px" />
          </el-form-item>
          <el-form-item label="利差 %">
            <el-input-number v-model="form.spread" :step="0.0001" :precision="4"
                             :controls="false" style="width: 120px" />
          </el-form-item>
          <el-form-item label="起息日">
            <el-date-picker v-model="form.effectiveDate" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
          <el-form-item label="到期日">
            <el-date-picker v-model="form.maturityDate" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
          <el-form-item label="固定腿频率">
            <el-select v-model="form.fixedFreqMonths" style="width: 120px">
              <el-option :value="3" label="季度" />
              <el-option :value="12" label="年度" />
            </el-select>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- ② 市场数据 -->
      <el-card header="② 市场数据" shadow="never" style="margin-bottom: 12px">
        <el-form inline label-width="110px">
          <el-form-item label="估值日 t1">
            <el-date-picker v-model="form.valuationDate" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
          <el-form-item label="归因起始日 t0">
            <el-date-picker v-model="form.startDate" type="date" value-format="YYYY-MM-DD"
                            placeholder="选填,填了才能算归因" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" plain :loading="loadingMarket" @click="onLoadMarket">
              加载行情
            </el-button>
            <el-button type="primary" :loading="loadingValue" @click="onValue">
              计算估值
            </el-button>
            <el-button type="success" :loading="loadingAttr" :disabled="!form.startDate"
                       @click="onAttribution">
              计算归因
            </el-button>
          </el-form-item>
        </el-form>
        <el-alert v-if="marketApprox" type="warning" :closable="false"
                  title="当前日期在交易日历数据范围之外,日历按周末规则近似" style="margin-bottom: 8px" />
        <el-table :data="curveRows" size="small" style="width: 100%">
          <el-table-column prop="tenor" label="期限" width="90" />
          <el-table-column label="零息利率 %">
            <template #default="{ row }">
              <el-input-number v-model="row.rate" :precision="4" :controls="false"
                               size="small" style="width: 120px" />
            </template>
          </el-table-column>
        </el-table>
        <div v-if="fixingInfo" style="margin-top: 8px; color: #909399; font-size: 13px">
          当期定盘:{{ form.benchmark === 'FR007' ? 'FR007' : 'Shibor 3M' }}
          {{ fixingInfo.date }} = {{ fixingInfo.rate }}%
        </div>
      </el-card>

      <!-- ③ 结果区 -->
      <el-card v-if="warnings.length" shadow="never" style="margin-bottom: 12px">
        <el-alert v-for="(w, i) in warnings" :key="i" :title="w" type="warning"
                  :closable="false" style="margin-bottom: 4px" />
      </el-card>

      <el-card v-if="valueResult" shadow="never" style="margin-bottom: 12px">
        <template #header>③ 估值结果</template>
        <el-row :gutter="12">
          <el-col :span="6"><stat-card title="NPV(元)" :v="valueResult.npv" /></el-col>
          <el-col :span="6"><stat-card title="固定腿 PV(元)" :v="valueResult.pv_fixed" /></el-col>
          <el-col :span="6"><stat-card title="浮动腿 PV(元)" :v="valueResult.pv_floating" /></el-col>
          <el-col :span="6"><stat-card title="平行 DV01(元/bp)" :v="valueResult.dv01_parallel" /></el-col>
        </el-row>
      </el-card>

      <el-tabs v-model="activeTab" style="margin-bottom: 24px">
        <el-tab-pane label="关键期限 DV01" name="krdv">
          <el-table v-if="valueResult" :data="valueResult.krdv01" size="small">
            <el-table-column prop="tenor" label="期限" width="90" />
            <el-table-column prop="dv01" label="KRDV01(元/bp)">
              <template #default="{ row }">{{ fmt(row.dv01) }}</template>
            </el-table-column>
          </el-table>
          <div v-if="valueResult" style="color:#909399;font-size:13px;margin-top:6px">
            合计 = {{ fmt(krdvSum) }};应等于平行 DV01
          </div>
        </el-tab-pane>

        <el-tab-pane label="现金流明细" name="cf">
          <template v-if="valueResult">
            <h4>固定腿</h4>
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
            <h4 style="margin-top:16px">浮动腿(展开行查看重置子区间)</h4>
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
                  <div style="color:#909399;font-size:13px">勾稽校验</div>
                  <div :style="{ color: attributionResult.identity.ok ? '#67c23a' : '#f56c6c' }">
                    {{ attributionResult.identity.ok ? '通过' : '失败' }}
                    (差 {{ attributionResult.identity.diff.toExponential(2) }})
                  </div>
                </el-card>
              </el-col>
            </el-row>
            <el-table :data="attrRows" size="small" border>
              <el-table-column prop="label" label="分项" width="220" />
              <el-table-column label="金额(元)" align="right">
                <template #default="{ row }">{{ fmt(row.value) }}</template>
              </el-table-column>
              <el-table-column label="含义" />
            </el-table>
            <h4 style="margin-top:16px">曲线效应明细</h4>
            <el-table :data="attributionResult.detail" size="small" border>
              <el-table-column prop="tenor" label="期限" width="90" />
              <el-table-column label="Δy(bp)" align="right">
                <template #default="{ row }">{{ row.dy_bp.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column label="KRDV01(元/bp)" align="right">
                <template #default="{ row }">{{ fmt(row.krdv01) }}</template>
              </el-table-column>
              <el-table-column label="贡献(元)" align="right">
                <template #default="{ row }">{{ fmt(row.contribution) }}</template>
              </el-table-column>
            </el-table>
          </template>
        </el-tab-pane>
      </el-tabs>
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, defineComponent, h, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { loadMarket, postAttribution, postValue } from '../api/client'

const StatCard = defineComponent({
  props: { title: String, v: Number },
  setup(props) {
    return () => h('el-card', { shadow: 'never' }, () => [
      h('div', { style: 'color:#909399;font-size:13px' }, props.title),
      h('div', {
        style: `font-size:20px;font-weight:600;color:${props.v < 0 ? '#f56c6c' : '#303133'}`,
      }, formatNumber(props.v)),
    ])
  },
})

function formatNumber(v) {
  if (v == null || Number.isNaN(v)) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const form = ref({
  benchmark: 'FR007', direction: 'receiver', notional: 100000000,
  fixedRate: 1.65, spread: 0.0,
  effectiveDate: '2026-06-01', maturityDate: '2026-12-01',
  fixedFreqMonths: 3, valuationDate: '2026-11-06', startDate: '',
})
const curveRows = ref([])
const fixingInfo = ref(null)
const marketApprox = ref(false)
const loadingMarket = ref(false)
const loadingValue = ref(false)
const loadingAttr = ref(false)
const valueResult = ref(null)
const attributionResult = ref(null)
const warnings = ref([])
const activeTab = ref('krdv')

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
  }
}

function errText(e) {
  const d = e?.response?.data?.detail
  return typeof d === 'string' ? d : '请求失败'
}

async function onLoadMarket() {
  loadingMarket.value = true
  try {
    const m = await loadMarket(form.value.benchmark, form.value.valuationDate)
    curveRows.value = m.curve.map(x => ({ ...x }))
    fixingInfo.value = m.fixing
    marketApprox.value = m.calendar_approximate
    valueResult.value = null
    attributionResult.value = null
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
    const p = { ...payload(), start_date: form.value.startDate }
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
