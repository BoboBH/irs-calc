import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 30000 })

export const loadMarket = (benchmark, date) =>
  http.get('/market', { params: { benchmark, date } }).then(r => r.data)

export const postValue = (payload) =>
  http.post('/value', payload).then(r => r.data)

export const postAttribution = (payload) =>
  http.post('/attribution', payload).then(r => r.data)

export const postParRate = (payload) =>
  http.post('/par_rate', payload).then(r => r.data)
