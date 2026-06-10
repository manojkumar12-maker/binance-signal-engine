import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || ''
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''

export const supabase = createClient(supabaseUrl, supabaseKey)

export async function getActiveSignals() {
  const { data, error } = await supabase
    .from('signals')
    .select('*')
    .eq('executed', false)
    .order('created_at', { ascending: false })
    .limit(10)
  
  if (error) {
    console.error('Error fetching signals:', error)
    return []
  }
  
  return data || []
}

export async function getRecentTrades() {
  const { data, error } = await supabase
    .from('trades')
    .select('*')
    .order('created_at', { ascending: false })
    .limit(10)
  
  if (error) {
    console.error('Error fetching trades:', error)
    return []
  }
  
  return data || []
}

export async function getAnalytics() {
  const { data, error } = await supabase
    .from('analytics')
    .select('*')
    .order('created_at', { ascending: false })
    .limit(100)
  
  if (error) {
    console.error('Error fetching analytics:', error)
    return []
  }
  
  return data || []
}

export function subscribeToSignals(callback: (payload: any) => void) {
  const channel = supabase
    .channel('signals')
    .on('postgres_changes', { 
      event: 'INSERT', 
      schema: 'public', 
      table: 'signals' 
    }, payload => {
      callback(payload.new)
    })
    .subscribe()
  
  return () => {
    supabase.removeChannel(channel)
  }
}
