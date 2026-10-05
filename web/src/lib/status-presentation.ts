type StatusBadge = { label: string; className: string };

type StatusLabels = Record<string, string>;

const listingLabels: StatusLabels = {
  draft: "Черновик",
  pending_review: "На проверке",
  rejected: "Нужно исправить",
  active: "Опубликовано",
  paused: "Снято с публикации",
  sold: "Продано",
  archived: "В архиве",
  blocked: "Заблокировано"
};

const companyLabels: StatusLabels = {
  pending: "На проверке",
  approved: "Допущена к пилоту",
  rejected: "Нужно исправить",
  blocked: "Доступ заблокирован"
};

const reportLabels: StatusLabels = {
  open: "Открыта",
  resolved: "Рассмотрена"
};

function badge(status: string, labels: StatusLabels): StatusBadge {
  const label = labels[status];
  return {
    label: label || "Неизвестный статус",
    className: `status-pill status-${label ? status : "unknown"}`
  };
}

export const listingStatusBadge = (status: string) => badge(status, listingLabels);
export const companyStatusBadge = (status: string) => badge(status, companyLabels);
export const reportStatusBadge = (status: string) => badge(status, reportLabels);
