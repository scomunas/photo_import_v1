import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, of } from 'rxjs';

export interface SystemStatus {
  status: string;
  database: string;
  nas: string;
  version: string;
}

@Injectable({
  providedIn: 'root'
})
export class StatusService {
  private apiUrl = ((window as any).__env?.apiUrl || 'http://localhost:8080') + '/health';

  constructor(private http: HttpClient) { }

  getSystemStatus(): Observable<SystemStatus> {
    return this.http.get<SystemStatus>(this.apiUrl).pipe(
      catchError(error => {
        console.error('Error fetching system status', error);
        return of({
          status: 'offline',
          database: 'offline',
          nas: 'offline',
          version: '0.0.0'
        });
      })
    );
  }
}
