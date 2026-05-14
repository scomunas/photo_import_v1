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

export interface PaginatedFiles {
  total: number;
  pending_total: number;
  data: ProcessedFile[];
}

@Injectable({
  providedIn: 'root'
})
export class FileService {
  private apiUrl = ((window as any).__env?.apiUrl || 'http://localhost:8080') + '/files';

  constructor(private http: HttpClient) { }

  getFiles(limit: number, offset: number, filters?: any): Observable<PaginatedFiles> {
    let params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString());
      
    if (filters) {
      if (filters.status) params = params.set('status', filters.status);
      if (filters.filename) params = params.set('filename', filters.filename);
      if (filters.source_path) params = params.set('source_path', filters.source_path);
      if (filters.action) params = params.set('action', filters.action);
    }
    
    return this.http.get<PaginatedFiles>(this.apiUrl, { params });
  }

  processFile(fileId: number): Observable<any> {
    return this.http.post(`${this.apiUrl}/${fileId}/process`, {});
  }

  processAllFiles(filters: any): Observable<any> {
    return this.http.post(`${this.apiUrl}/process-all`, filters);
  }

  updateFile(fileId: number, data: Partial<ProcessedFile>): Observable<any> {
    return this.http.put(`${this.apiUrl}/${fileId}`, data);
  }
}
