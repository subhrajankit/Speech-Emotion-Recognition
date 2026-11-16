import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'accent' | 'neutral';
  className?: string;
  style?: React.CSSProperties;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'default',
  className = '',
  style = {},
}) => {
  return (
    <span
      className={`badge badge-${variant} ${className}`}
      style={style}
    >
      {children}
    </span>
  );
};
