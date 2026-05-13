import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ProcessedFile {
  id: number;
  original_path: string;
  original_filename: string;
  target_path: string;
  target_filename: string;
  date_taken: string;
  action: string;
  status: string;
  error_details?: string;
  processed_at?: string;
  created_at: string;
}

@Injectable({
  providedIn: 'root'
})
export class FileService {
  private apiUrl = ((window as any).__env?.apiUrl || 'http://localhost:8080') + '/files';

  constructor(private http: HttpClient) { }

  getFiles(status?: string): Observable<ProcessedFile[]> {
    let params = new HttpParams();
    if (status) params = params.set('status', status);
    return this.http.get<ProcessedFile[]>(this.apiUrl, { params });
  }

  processFile(fileId: number): Observable<any> {
    return this.http.post(`${this.apiUrl}/${fileId}/process`, {});
  }

  updateFile(fileId: number, data: Partial<ProcessedFile>): Observable<any> {
    return this.http.put(`${this.apiUrl}/${fileId}`, data);
  }
}
