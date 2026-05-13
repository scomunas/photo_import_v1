import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ImportConfig {
  id: number;
  source_path: string;
  target_path: string;
  path_template: string;
  name_template: string;
  action: string;
  import_status?: string;
}

@Injectable({
  providedIn: 'root'
})
export class ConfigService {
  private apiUrl = 'http://localhost:8080/configs';

  constructor(private http: HttpClient) { }

  getConfigs(): Observable<ImportConfig[]> {
    return this.http.get<ImportConfig[]>(this.apiUrl);
  }

  addConfig(config: any): Observable<any> {
    return this.http.post(this.apiUrl, config);
  }

  updateConfig(id: number, config: ImportConfig): Observable<any> {
    return this.http.put(`${this.apiUrl}/${id}`, config);
  }

  triggerScan(id: number): Observable<any> {
    return this.http.post(`${this.apiUrl}/${id}/scan`, {});
  }

  getScans(id: number): Observable<any[]> {
    return this.http.get<any[]>(`${this.apiUrl}/${id}/scans`);
  }

  triggerImport(id: number): Observable<any> {
    return this.http.post(`${this.apiUrl}/${id}/import`, {});
  }
}
