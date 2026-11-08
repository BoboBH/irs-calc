import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import App from './App.vue'

// 深色终端主题:EP 组件走官方 dark css-vars,html.dark 必须在挂载前加好
document.documentElement.classList.add('dark')
createApp(App).use(ElementPlus, { locale: zhCn }).mount('#app')
