import React from 'react';
import { ComponentStatus } from '../../types/speech';

export interface StatusDotProps {
  status: ComponentStatus | 'connected' | 'connecting' | 'reconnecting' | 'disconnected' | 'error';
  size?: number;
  pulse?: boolean;
}

export const StatusDot: React.FC<StatusDotProps> = ({
  status,
  size = 8,
  pulse = false,
}) => {
  const getColor = (): string => {
    switch (status) {
      case 'ok':
      case 'connected':
        return 'var(--color-success)';
      case 'degraded':
      case 'connecting':
      case 'reconnecting':
        return 'var(--color-energy)';
      case 'unhealthy':
      case 'error':
      case 'offline':
        return 'var(--color-danger)';
      case 'not_configured':
      case 'disconnected':
      default:
        return 'var(--text-muted)';
    }
  };

  const color = getColor();

  return (
    <span
      style={{
        position: 'relative',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: `${size}px`,
        height: `${size}px`,
      }}
    >
      {pulse && (
        <span
          style={{
            position: 'absolute',
            width: '100%',
            height: '100%',
            borderRadius: '50%',
            backgroundColor: color,
            opacity: 0.6,
            animation: 'ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite',
          }}
        />
      )}
      <span
        style={{
          display: 'inline-block',
          width: `${size}px`,
          height: `${size}px`,
          borderRadius: '50%',
          backgroundColor: color,
        }}
      />
    </span>
  );
};
