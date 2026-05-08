car_data=read.csv("car data.csv")
library(carData)
library(car)

head(car_data)
tail(car_data)
colnames(car_data)
str(car_data)

car_data$Year=as.ts(car_data$Year)
car_data$Owner=as.factor(car_data$Owner)

hist(car_data$Selling_Price)
hist(car_data$Kms_Driven)
