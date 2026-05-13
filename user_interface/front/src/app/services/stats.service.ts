import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface KPI {
  status: string;
  count: number;
}

export interface DailyStat {
  day: string;
  status: string;
  count: number;
}

@Injectable({
  providedIn: 'root'
})
export class StatsService {
  private apiUrl = ((window as any).__env?.apiUrl || 'http://localhost:8080') + '/stats';

  constructor(private http: HttpClient) { }

  getKPIs(startDate?: string, endDate?: string): Observable<KPI[]> {
    let params = new HttpParams();
    if (startDate) params = params.set('start_date', startDate);
    if (endDate) params = params.set('end_date', endDate);
    return this.http.get<KPI[]>(`${this.apiUrl}/kpis`, { params });
  }

  getDailyStats(startDate?: string, endDate?: string): Observable<DailyStat[]> {
    let params = new HttpParams();
    if (startDate) params = params.set('start_date', startDate);
    if (endDate) params = params.set('end_date', endDate);
    return this.http.get<DailyStat[]>(`${this.apiUrl}/daily`, { params });
  }
}
