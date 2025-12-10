import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export class BaseService {
  protected baseUrl = 'http://localhost:8000/api';

  constructor(protected http: HttpClient) {}

  protected get(endpoint: string, params?: HttpParams): Observable<any> {
    return this.http.get(`${this.baseUrl}${endpoint}`, { params });
  }

  protected post(endpoint: string, body: any, params?: HttpParams): Observable<any> {
    return this.http.post(`${this.baseUrl}${endpoint}`, body, { params });
  }
}