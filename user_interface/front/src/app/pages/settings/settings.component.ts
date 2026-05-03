import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ConfigService, ImportConfig } from '../../services/config.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.css'
})
export class SettingsComponent implements OnInit {
  configs: ImportConfig[] = [];
  editingId: number | null = null;
  isAdding = false;
  tempConfig: any = null;

  constructor(private configService: ConfigService) {}

  ngOnInit() {
    this.loadConfigs();
  }

  loadConfigs() {
    this.configService.getConfigs().subscribe(res => {
      this.configs = res;
    });
  }

  startAdd() {
    this.isAdding = true;
    this.editingId = null;
    this.tempConfig = {
      source_path: '',
      target_path: '',
      path_template: '{year}/{month}',
      name_template: '{filename}',
      action: 'move'
    };
  }

  startEdit(config: ImportConfig) {
    this.isAdding = false;
    this.editingId = config.id;
    this.tempConfig = { ...config };
  }

  cancelEdit() {
    this.editingId = null;
    this.isAdding = false;
    this.tempConfig = null;
  }

  saveEdit() {
    if (this.tempConfig) {
      if (this.isAdding) {
        this.configService.addConfig(this.tempConfig).subscribe(() => {
          this.loadConfigs();
          this.cancelEdit();
        });
      } else if (this.editingId) {
        this.configService.updateConfig(this.editingId, this.tempConfig).subscribe(() => {
          this.loadConfigs();
          this.cancelEdit();
        });
      }
    }
  }
}
