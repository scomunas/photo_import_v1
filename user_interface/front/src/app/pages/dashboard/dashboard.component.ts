import { Component, OnInit, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { StatsService, KPI, DailyStat } from '../../services/stats.service';
import Chart from 'chart.js/auto';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css'
})
export class DashboardComponent implements OnInit, AfterViewInit {
  @ViewChild('statsChart') statsChartCanvas!: ElementRef;
  
  startDate: string = '';
  endDate: string = '';
  
  kpis = {
    received: 0,
    completed: 0,
    pending: 0,
    error: 0
  };
  
  chart: any;

  constructor(private statsService: StatsService) {
    // Inicializar fechas con el último mes
    const end = new Date();
    const start = new Date();
    start.setMonth(start.getMonth() - 1);
    
    this.endDate = end.toISOString().split('T')[0];
    this.startDate = start.toISOString().split('T')[0];
  }

  ngOnInit() {
    this.loadData();
  }

  ngAfterViewInit() {
    this.initChart();
  }

  loadData() {
    this.statsService.getKPIs(this.startDate, this.endDate).subscribe(res => {
      this.resetKPIs();
      res.forEach(k => {
        if (k.status === 'pending') this.kpis.pending = k.count;
        else if (k.status === 'completed' || k.status === 'success') this.kpis.completed = k.count;
        else if (k.status === 'error') this.kpis.error = k.count;
      });
      this.kpis.received = this.kpis.pending + this.kpis.completed + this.kpis.error;
    });

    this.statsService.getDailyStats(this.startDate, this.endDate).subscribe(res => {
      this.updateChart(res);
    });
  }

  resetKPIs() {
    this.kpis = { received: 0, completed: 0, pending: 0, error: 0 };
  }

  initChart() {
    const ctx = this.statsChartCanvas.nativeElement.getContext('2d');
    this.chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [
          { 
            label: 'Completed', data: [], 
            backgroundColor: '#ecfdf5', borderColor: '#10b981', 
            borderWidth: 1, borderRadius: 6, stack: 'Stack 0' 
          },
          { 
            label: 'Pending', data: [], 
            backgroundColor: '#fffbeb', borderColor: '#f59e0b', 
            borderWidth: 1, borderRadius: 6, stack: 'Stack 0' 
          },
          { 
            label: 'Error', data: [], 
            backgroundColor: '#fef2f2', borderColor: '#ef4444', 
            borderWidth: 1, borderRadius: 6, stack: 'Stack 0' 
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top' }
        },
        scales: {
          x: { stacked: true },
          y: { stacked: true, beginAtZero: true }
        }
      }
    });
  }

  updateChart(data: DailyStat[]) {
    if (!this.chart) return;

    const days = [...new Set(data.map(d => d.day))].sort();
    const completedData = days.map(day => {
      const found = data.find(d => d.day === day && (d.status === 'completed' || d.status === 'success'));
      return found ? found.count : 0;
    });
    const pendingData = days.map(day => {
      const found = data.find(d => d.day === day && d.status === 'pending');
      return found ? found.count : 0;
    });
    const errorData = days.map(day => {
      const found = data.find(d => d.day === day && d.status === 'error');
      return found ? found.count : 0;
    });

    this.chart.data.labels = days;
    this.chart.data.datasets[0].data = completedData;
    this.chart.data.datasets[1].data = pendingData;
    this.chart.data.datasets[2].data = errorData;
    this.chart.update();
  }

  onFilterChange() {
    this.loadData();
  }
}
